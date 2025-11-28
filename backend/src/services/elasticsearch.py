import json
from typing import Any, Dict, List, Optional

from elasticsearch import Elasticsearch, exceptions
from loguru import logger

from ..configs.setup import get_backend_settings

settings = get_backend_settings()


class ElasticsearchClient:

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        index_name: str = "medical_documents",
    ):

        self.host = host if host is not None else settings.elasticsearch_host
        self.port = port if port is not None else settings.elasticsearch_port
        self.index_name = index_name

        try:
            # Force compatibility with Elasticsearch 8.x (server version)
            self.client = Elasticsearch(
                [f"http://{self.host}:{self.port}"],
                verify_certs=False,
                request_timeout=30,
                headers={
                    "Accept": "application/vnd.elasticsearch+json; compatible-with=8"
                },
            )
            # Test connection
            if self.client.ping():
                logger.info(f"Connected to Elasticsearch at {self.host}:{self.port}")
            else:
                logger.error("Failed to ping Elasticsearch")
        except exceptions.ConnectionError as e:
            logger.error(f"Failed to connect to Elasticsearch: {e}")
            raise

    def create_index(self, settings_override: Optional[Dict] = None) -> bool:
        """
        Create Elasticsearch index with Vietnamese text analyzer.

        Vietnamese Analyzer Configuration:
        - Custom tokenizer for Vietnamese text
        - Lowercase normalization
        - ASCII folding for diacritics
        - Vietnamese stop words
        - Edge n-gram for partial matching
        """
        index_settings = {
            "settings": {
                "number_of_shards": 2,
                "number_of_replicas": 1,
                "analysis": {
                    "filter": {
                        "vietnamese_stop": {
                            "type": "stop",
                            "stopwords": [
                                "và",
                                "của",
                                "có",
                                "các",
                                "được",
                                "trong",
                                "cho",
                                "từ",
                                "với",
                                "này",
                                "đó",
                                "là",
                                "một",
                                "những",
                                "người",
                                "đến",
                                "để",
                                "sau",
                                "trước",
                                "khi",
                            ],
                        },
                        "edge_ngram_filter": {
                            "type": "edge_ngram",
                            "min_gram": 2,
                            "max_gram": 15,
                        },
                    },
                    "analyzer": {
                        "vietnamese_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": [
                                "lowercase",
                                "asciifolding",
                                "vietnamese_stop",
                                "snowball",
                            ],
                        },
                        "vietnamese_search_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": [
                                "lowercase",
                                "asciifolding",
                                "vietnamese_stop",
                            ],
                        },
                    },
                },
            },
            "mappings": {
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "document_id": {"type": "keyword"},
                    "chunk_index": {"type": "integer"},
                    "content": {
                        "type": "text",
                        "analyzer": "vietnamese_analyzer",
                        "search_analyzer": "vietnamese_search_analyzer",
                        "fields": {
                            "keyword": {"type": "keyword"},
                            "ngram": {
                                "type": "text",
                                "analyzer": "vietnamese_analyzer",
                            },
                        },
                    },
                    "title": {
                        "type": "text",
                        "analyzer": "vietnamese_analyzer",
                        "search_analyzer": "vietnamese_search_analyzer",
                    },
                    "doc_type": {"type": "keyword"},
                    "source": {"type": "keyword"},
                    "language": {"type": "keyword"},
                    "metadata": {"type": "object", "enabled": False},
                    "created_at": {"type": "date"},
                }
            },
        }

        if settings_override:
            index_settings.update(settings_override)

        try:
            if self.client.indices.exists(index=self.index_name):
                logger.warning(f"Index '{self.index_name}' already exists")
                return True

            self.client.indices.create(index=self.index_name, body=index_settings)
            logger.info(f"Created index '{self.index_name}' with Vietnamese analyzer")
            return True
        except exceptions.RequestError as e:
            logger.error(f"Error creating index: {e}")
            return False

    def index_chunk(
        self,
        chunk_id: str,
        document_id: str,
        chunk_index: int,
        content: str,
        title: str,
        doc_type: str = "medical_qa",
        source: str = "",
        language: str = "vi",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        doc = {
            "chunk_id": str(chunk_id),
            "document_id": str(document_id),
            "chunk_index": chunk_index,
            "content": content,
            "title": title,
            "doc_type": doc_type,
            "source": source,
            "language": language,
            "metadata": metadata or {},
        }

        try:
            response = self.client.index(
                index=self.index_name, id=str(chunk_id), body=doc
            )
            if response["result"] in ["created", "updated"]:
                logger.debug(f"Indexed chunk {chunk_id} in Elasticsearch")
                return True
            else:
                logger.warning(
                    f"Unexpected response indexing chunk {chunk_id}: {response}"
                )
                return False
        except exceptions.RequestError as e:
            logger.error(f"Error indexing chunk {chunk_id}: {e}")
            return False

    def search_bm25(
        self,
        query: str,
        top_k: int = settings.top_k,
        doc_type_filter: Optional[str] = None,
        source_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        must_clauses = [
            {
                "multi_match": {
                    "query": query,
                    "fields": ["content^2", "title"],
                    "type": "best_fields",
                    "operator": "or",
                }
            }
        ]

        filter_clauses = []
        if doc_type_filter:
            filter_clauses.append({"term": {"doc_type": doc_type_filter}})
        if source_filter:
            filter_clauses.append({"term": {"source": source_filter}})

        search_body = {
            "query": {
                "bool": {
                    "must": must_clauses,
                    "filter": filter_clauses if filter_clauses else [],
                }
            },
            "size": top_k,
            "_source": [
                "chunk_id",
                "document_id",
                "chunk_index",
                "content",
                "title",
                "doc_type",
                "source",
                "metadata",
            ],
        }

        try:
            response = self.client.search(index=self.index_name, body=search_body)

            results = []
            for hit in response["hits"]["hits"]:
                result = {
                    "chunk_id": hit["_source"]["chunk_id"],
                    "document_id": hit["_source"]["document_id"],
                    "chunk_index": hit["_source"]["chunk_index"],
                    "content": hit["_source"]["content"],
                    "title": hit["_source"]["title"],
                    "doc_type": hit["_source"]["doc_type"],
                    "source": hit["_source"]["source"],
                    "metadata": hit["_source"].get("metadata", {}),
                    "score": hit["_score"],
                    "search_type": "keyword",
                }
                results.append(result)

            logger.debug(
                f"BM25 search returned {len(results)} results for query: {query[:50]}..."
            )
            return results
        except exceptions.RequestError as e:
            logger.error(f"Error performing BM25 search: {e}")
            return []

    def delete_document_chunks(self, document_id: str) -> int:
        query = {"query": {"term": {"document_id": str(document_id)}}}

        try:
            response = self.client.delete_by_query(index=self.index_name, body=query)
            deleted: int = response.get("deleted", 0)
            logger.info(f"Deleted {deleted} chunks for document {document_id}")
            return deleted
        except exceptions.RequestError as e:
            logger.error(f"Error deleting document chunks: {e}")
            return 0

    def get_index_stats(self) -> Dict[str, Any]:
        try:
            stats = self.client.indices.stats(index=self.index_name)
            return {
                "document_count": stats["_all"]["primaries"]["docs"]["count"],
                "index_size_bytes": stats["_all"]["primaries"]["store"][
                    "size_in_bytes"
                ],
                "index_name": self.index_name,
            }
        except exceptions.RequestError as e:
            logger.error(f"Error getting index stats: {e}")
            return {"error": str(e)}


_es_client_instance = None


def get_elasticsearch_client() -> ElasticsearchClient:
    global _es_client_instance
    if _es_client_instance is None:
        _es_client_instance = ElasticsearchClient()
    return _es_client_instance
