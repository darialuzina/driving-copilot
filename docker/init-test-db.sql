-- Create the test database alongside the dev database at container init.
-- Both live in the same Postgres instance, isolated by database name.
CREATE DATABASE driving_copilot_test;
GRANT ALL PRIVILEGES ON DATABASE driving_copilot_test TO app;
