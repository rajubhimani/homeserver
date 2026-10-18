<?php
// Database login from the environment (.env via compose), the same pattern
// as the image's own redis.config.php / smtp.config.php: Nextcloud merges
// every *.config.php over config.php. Without it, Nextcloud keeps the
// `oc_<admin>` role and generated password its installer wrote into
// config.php, which exist only in that one database server.
if (getenv('POSTGRES_HOST') && getenv('POSTGRES_USER')) {
  $CONFIG = array(
    'dbtype' => 'pgsql',
    'dbhost' => getenv('POSTGRES_HOST'),
    'dbname' => getenv('POSTGRES_DB'),
    'dbuser' => getenv('POSTGRES_USER'),
    'dbpassword' => getenv('POSTGRES_PASSWORD'),
  );
}
