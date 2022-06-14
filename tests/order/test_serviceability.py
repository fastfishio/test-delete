from liborder import Context, domain


def test_nonserviceable():
    with Context.service(lang="en", country_code="AE", lat=261990115, lng=552579175):
        serviceability = domain.serviceability.GetServiceability().execute()
        assert not serviceability.serviceable, "Found warehouse in non serviceable area"


def test_one_warehouse():
    with Context.service(lang="en", country_code="AE", lat=251944818, lng=552744380):
        serviceability = domain.serviceability.GetServiceability().execute()
        assert serviceability.serviceable, "No warehouse found in serviceable area"

#TODO: Add more meaningful tests based on multi-warehouse serviceability model
