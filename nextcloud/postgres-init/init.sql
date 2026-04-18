-- Grant full schema privileges to the nextcloud user
-- Required for PostgreSQL 15+ where public schema privileges changed
GRANT ALL ON SCHEMA public TO nextcloud;
ALTER SCHEMA public OWNER TO nextcloud;
