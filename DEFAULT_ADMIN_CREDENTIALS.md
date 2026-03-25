# Default CKAN Admin Credentials

The Docker `ckan-app` service bootstraps a sysadmin using these defaults:

- username: `ckan_admin`
- password: `test1234`

These values come from `CKAN_SYSADMIN_NAME` and `CKAN_SYSADMIN_PASSWORD` in `docker/docker-compose.test.yml`.

Important behavior:

- CKAN startup only creates this user if it does not already exist.
- If the user already exists, startup does not overwrite the account or password.
