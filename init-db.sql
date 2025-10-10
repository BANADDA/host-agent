-- TAOLIE Host Agent Database Initialization Script

-- Create database if it doesn't exist
SELECT 'CREATE DATABASE taolie_host_agent'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'taolie_host_agent')\gexec

-- Connect to the database
\c taolie_host_agent;

-- Create user if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'agent') THEN
        CREATE ROLE agent WITH LOGIN PASSWORD 'taolie_agent_password';
    END IF;
END
$$;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE taolie_host_agent TO agent;
GRANT ALL ON SCHEMA public TO agent;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO agent;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO agent;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO agent;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO agent;
