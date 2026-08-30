-- Synthetic local runtime only. Production roles and passwords must be supplied
-- through an approved database bootstrap process; these are not real secrets.
CREATE ROLE jcareer_member_app LOGIN PASSWORD 'synthetic-member-db-password';
CREATE ROLE jcareer_company_app LOGIN PASSWORD 'synthetic-company-db-password';

CREATE DATABASE jcareer_member OWNER jcareer_member_app;
CREATE DATABASE jcareer_company OWNER jcareer_company_app;

REVOKE CONNECT, TEMPORARY ON DATABASE jcareer_member FROM PUBLIC;
REVOKE CONNECT, TEMPORARY ON DATABASE jcareer_company FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE jcareer_member TO jcareer_member_app;
GRANT CONNECT, TEMPORARY ON DATABASE jcareer_company TO jcareer_company_app;
