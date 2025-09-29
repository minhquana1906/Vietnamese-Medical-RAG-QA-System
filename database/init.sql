DO
$$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_database WHERE datname = 'chat_conversation_db'
   ) THEN
      PERFORM dblink_exec(
         'dbname=' || current_database(),
         'CREATE DATABASE chat_conversation_db
            ENCODING ''UTF8''
            LC_COLLATE ''en_US.UTF-8''
            LC_CTYPE ''en_US.UTF-8''
            TEMPLATE template0'
      );
   END IF;
END
$$;
