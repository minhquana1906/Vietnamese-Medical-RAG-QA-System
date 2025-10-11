class TestUtilityFunctions:
    def test_generate_hash(self):
        from backend.src.utils import generate_hash

        hash1 = generate_hash()
        hash2 = generate_hash()

        assert hash1 != hash2
        assert len(hash1) == 16

        hash_custom = generate_hash(length=32)
        assert len(hash_custom) == 32

    def test_generate_request_id(self):
        from backend.src.utils import generate_request_id

        id1 = generate_request_id()
        id2 = generate_request_id()

        assert id1 != id2
        assert len(id1) == 33

        id_custom = generate_request_id(max_length=16)
        assert len(id_custom) == 17  # 16 + 1
