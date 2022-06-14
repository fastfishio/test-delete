# mp-boilerplate-api ![](https://github.com/fastfishio/mp-boilerplate-api/workflows/tests/badge.svg)

Barebones marketplace application to start new marketplaces within noon ecosystem.
Thank you to the [mp-instant-api](https://github.com/fastfishio/mp-instant-api) team for the base code structure

Let's write the future together!

## Getting Started: Rename
1. Replace all instances of below with a reference to your marketplace
   1. `BOILERPLATE`
   2. `boilerplate`
   3. `Boilerplate`

2. Rename files
   1. `src/liborder/domain/boilerplate_event.py`
   2. `tests/data/spanner/boilerplate.toml`
   3. `skaffold/mp-boilerplate-*.yaml`

### What Rename Entails 
Including but not limited to:
1. Infra Mp Setup
2. Spanner Instance `boilerplate01`
3. Spanner database `boilerplate`
4. KML Serviceability Bucket `noonstg-mp-gcs-boilerplate-kml`
5. Libexternal Invoicing URL `boilerplate`
6. Libexternal Notification Tenant Code `boilerplate`
7. Support in Wallet/Credit for `boilerplate_goodwill` ref type
8. Creation of appropriate pubsub topics and subscribers (e.g. `mp_boilerplate-api`, `boilerplate_price`, etc.)
9. All MySQL Table and Databases
10. CMS Bucket `noonstg-mp-gcs-boilerplate-cms`
11. KML Bucket `noonstg-mp-gcs-boilerplate-kml`
12. MP CODE `boilerplate`


### MP-Payment Integration
1. Make sure the MP_CODE is registered as a valid marketplace. [Sample](https://github.com/fastfishio/mp-payment/pull/295)

### Infra Setup
1. [Devops] Workload Identity (infra-mp). [Sample](https://github.com/fastfishio/infra-mp/pull/4701)
2. [Devops] Pubsub. [Sample](https://github.com/fastfishio/kapitan-noongcp-sensi/commit/e766021ac13a602164b47e7390e3665e14e48643)
3. [Dev] Apps Targets (infra-mp).
   1. [Base Sample](https://github.com/fastfishio/infra-mp/blob/master/platform/targets/apps/base/boilerplate.yml) : To manage shared env
   2. [App Sample](https://github.com/fastfishio/infra-mp/blob/master/platform/targets/apps/boilerplate/mp-boilerplate-api-order.yml) : To manage services & deployment
   3. [Repo Sample](https://github.com/fastfishio/infra-mp/blob/master/platform/targets/apps/repos/repo-mp-boilerplate-api.yml) : To manage permission
4. [Devops + Devs] Database
   1. [kapitan-infra](https://github.com/fastfishio/kapitan-infra/blob/master/inventory/targets/staging-sql.yml) : Ask devops to create db here (only devops can access), make sure to use mysql8
   2. [infra-mp](https://github.com/fastfishio/infra-mp/pull/4752) : Create db target here
   3. [SQL Platform](https://sql-platform.noonstg.team/sdb) : For granting access to your service and your email on the db (eg. grant access to `mp-boilerplate-api@noonstg-mp` & `employee@noon.com` on `mpboilerplate` instance)
   4. Create the database schema, and insert tests data if needed. There are some options to do it:
      1. [mysqldump](https://dev.mysql.com/doc/refman/8.0/en/mysqldump.html) : manually from local to staging - this how boilerplate was setup
      2. [gh-ost](https://github.com/github/gh-ost) : appropriate for production that involves existing data migration
      3. [alembic](https://alembic.sqlalchemy.org) : alternative to gh-ost (do learn the tradeoff first)
5. [Dev] Solr (kapitan-solr)
   1. [Solr Repo](https://github.com/fastfishio/boilerplate-solr)
      1. Create marketplace-specific's own solr repo (by forking from boilerplate-solr, or from scratch)
      2. When creating repo, also create the build trigger [Trigger Sample](https://console.cloud.google.com/cloud-build/triggers/edit/0c0f53a1-8b81-46da-90c7-32b6d8e258e3?project=noon-core)
   2. [Master Sample](https://github.com/fastfishio/kapitan-solr/blob/master/platform/targets/apps/boilerplate/boilerplate-solr-search.yml)
   3. [Slave Sample](https://github.com/fastfishio/kapitan-solr/blob/master/platform/targets/apps/boilerplate/boilerplate-solr-search-slave.yml)
6. [Devops + Dev] Solr-proxy (infra-mp)
   1. [Master Sample](https://github.com/fastfishio/infra-mp/blob/master/platform/targets/apps/solr-proxy/boilerplate-solr-search-proxy.yml)
   2. [Slave Sample](https://github.com/fastfishio/infra-mp/blob/master/platform/targets/apps/solr-proxy/boilerplate-solr-search-slave-proxy.yml)
   3. Unauthorized : Ask devops to give `solr-admin` role to your account.
7. [Devops + Dev] Spanner
   1. Devops to create Spanner project,database, and instance if not yet exist.
   2. Dev to import the schema. [Schema Sample](https://github.com/fastfishio/mp-boilerplate-api/blob/main/tests/data/spanner/boilerplate.toml)
8. [Devops + Dev] Sentry
   1. Sentry Project needs to be created by devops (either on https://sentry.io/ or https://sentry.noon.team/)
   2. [infra-mp Sample](https://github.com/fastfishio/infra-mp/pull/4775) : Add that DSN as a secret.
9. [Devops] GCS Bucket
   1. [KML](https://console.cloud.google.com/storage/browser/noonstg-mp-gcs-boilerplate-kml;tab=objects?forceOnBucketsSortingFiltering=false&project=noonstg-mp-gcs) : Contains Servicable Lat-Lng
   2. [CMS](https://console.cloud.google.com/storage/browser/noonstg-mp-gcs-boilerplate-cms;tab=objects?forceOnBucketsSortingFiltering=false&project=noonstg-mp-gcs) : Make it public accessible (allUsers: legacyObjectReader & legacyBucketReader)

#### Important Notes
1. Always generate fixtures (make devTest) when making changes on infra. When facing 403 during devTest, request to devops for permission.
2. Always touch with bot after any PR to infra gets merged to apply changes.
3. There is incompatibility between mysqlclient v2.1.0 and the noonutil.engineutil v225. "Access Denied using password" error due to deprecation on passwd kwargs [read more](https://github.com/PyMySQL/mysqlclient/pull/513/files). Try to use mysqlclient v2.0.3 instead if that error persists. 

#### References
- [Application YAML](https://github.com/fastfishio/infra-docs/blob/master/Devs/application_yaml.md)
- [Deployment](https://github.com/fastfishio/infra-docs/blob/master/Devs/deployment.md)
- [Running Test / Adding Secret - Infra MP](https://github.com/fastfishio/infra-docs/blob/master/Devs/running_test_infra_mp.md#editing-a-secret-for-target-in-infra---mp)
