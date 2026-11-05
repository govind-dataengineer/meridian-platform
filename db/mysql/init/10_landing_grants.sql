-- The app user owns meridian_landing (created by MYSQL_DATABASE) and may only
-- READ the trusted course database. Least privilege from day one (Class 11).
GRANT SELECT ON meridian_retail.* TO 'meridian'@'%';
FLUSH PRIVILEGES;
