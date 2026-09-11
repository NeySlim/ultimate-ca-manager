"""The issuer-controlled pointer extensions of a leaf: CRL Distribution
Points, Authority Information Access (OCSP, caIssuers) and the CPS policy,
built from the CA's configuration the same way on every path (the CSR
trunk, the issue form, the timestamp signer, in-place renewal)."""

from cryptography import x509


def add_ca_pointer_extensions(builder: x509.CertificateBuilder, ca) -> x509.CertificateBuilder:
    """Embed the CA's CDP / AIA / CPS URLs when it publishes them."""
    if ca.cdp_enabled:
        cdp_urls = [u.replace('{ca_refid}', ca.url_ref) for u in ca.get_cdp_urls()]
        if cdp_urls:
            builder = builder.add_extension(
                x509.CRLDistributionPoints([
                    x509.DistributionPoint(
                        full_name=[x509.UniformResourceIdentifier(u)],
                        relative_name=None, reasons=None, crl_issuer=None,
                    ) for u in cdp_urls
                ]),
                critical=False,
            )
    aia = []
    if ca.ocsp_enabled:
        for uri in ca.get_ocsp_urls():
            aia.append(x509.AccessDescription(
                x509.oid.AuthorityInformationAccessOID.OCSP,
                x509.UniformResourceIdentifier(uri)))
    if ca.aia_ca_issuers_enabled:
        for url in ca.get_aia_urls():
            aia.append(x509.AccessDescription(
                x509.oid.AuthorityInformationAccessOID.CA_ISSUERS,
                x509.UniformResourceIdentifier(url.replace('{ca_refid}', ca.url_ref))))
    if aia:
        builder = builder.add_extension(
            x509.AuthorityInformationAccess(aia), critical=False)
    if ca.cps_enabled and ca.cps_uri:
        builder = builder.add_extension(
            x509.CertificatePolicies([
                x509.PolicyInformation(
                    policy_identifier=x509.ObjectIdentifier(ca.cps_oid or '2.5.29.32.0'),
                    policy_qualifiers=[ca.cps_uri],
                )
            ]),
            critical=False,
        )
    return builder
