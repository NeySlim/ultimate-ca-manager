/**
 * Ready-to-copy client configuration for a DNS UPDATE (RFC 2136) TSIG key.
 *
 * Option and variable names come from the client sources:
 *   nsupdate key file     bind9 bin/nsupdate/nsupdate.c read_sessionkey
 *   acme.sh               dnsapi/dns_nsupdate.sh (NSUPDATE_SERVER, _SERVER_PORT, _KEY, _ZONE)
 *   certbot               certbot_dns_rfc2136 (dns_rfc2136_server/port/name/secret/algorithm)
 *   lego                  providers/dns/rfc2136 (DNSUPDATE_NAMESERVER, DNSUPDATE_TSIG_*)
 *   cert-manager          ACMEIssuerDNS01ProviderRFC2136 (nameserver, tsigKeyName, ...)
 *   win-acme              plugin.validation.dns.rfc2136 (serverhost, tsigkey*)
 *   Posh-ACME             Plugins/RFC2136.ps1 (DDNSNameserver, DDNSPort, DDNSKey*)
 *
 * The client defaults (md5, sha1) are refused by UCM, so every snippet sets
 * the algorithm. The builder returns note keys, not text: the component
 * translates them.
 */

export const DNS_UPDATE_ALGORITHMS = ['hmac-sha256', 'hmac-sha384', 'hmac-sha512']

const IPV4 = /^\d{1,3}(\.\d{1,3}){3}$/

export const isIpAddress = (value) => IPV4.test(value || '') || (value || '').includes(':')

// cert-manager accepts HMACSHA256 and HMACSHA512 (HMACMD5 and HMACSHA1 too, refused by UCM).
export const certManagerAlgorithm = (algorithm) => {
  const value = algorithm.replace('-', '').toUpperCase()
  return value === 'HMACSHA256' || value === 'HMACSHA512' ? value : null
}

// win-acme parses the name of its TSigAlgorithm enum: Sha256, not hmac-sha256.
const winAcmeAlgorithm = (algorithm) => algorithm.replace('hmac-', '')

export function hostFromBase(base) {
  try {
    const host = new URL(base).hostname
    return host || 'ucm.example.com'
  } catch {
    return 'ucm.example.com'
  }
}

export function buildDnsUpdateSnippets({
  keyName,
  algorithm,
  secret,
  host = 'ucm.example.com',
  port = 53,
  directoryUrl = 'https://ucm.example.com/acme/proxy/<slug>/directory',
  domain = 'www.example.com',
  email = 'you@example.com',
}) {
  const certbotServer = isIpAddress(host) ? host : '<UCM-IP-address>'
  const keyFile = `key "${keyName}" {\n  algorithm ${algorithm};\n  secret "${secret}";\n};\n`
  const cmAlgorithm = certManagerAlgorithm(algorithm)

  const certManager = cmAlgorithm
    ? [
      'apiVersion: v1',
      'kind: Secret',
      'metadata:',
      '  name: ucm-rfc2136-tsig',
      '  namespace: cert-manager',
      'type: Opaque',
      'stringData:',
      `  tsig-secret: ${secret}`,
      '---',
      'apiVersion: cert-manager.io/v1',
      'kind: ClusterIssuer',
      'metadata:',
      '  name: ucm-proxy-rfc2136',
      'spec:',
      '  acme:',
      `    server: ${directoryUrl}`,
      `    email: ${email}`,
      '    privateKeySecretRef:',
      '      name: ucm-proxy-account-key',
      '    solvers:',
      '      - dns01:',
      '          rfc2136:',
      `            nameserver: ${host}:${port}`,
      `            tsigKeyName: ${keyName}`,
      `            tsigAlgorithm: ${cmAlgorithm}`,
      '            tsigSecretSecretRef:',
      '              name: ucm-rfc2136-tsig',
      '              key: tsig-secret',
      '',
    ].join('\n')
    : null

  return [
    {
      id: 'bind',
      code: keyFile,
      noteKeys: ['noteBind'],
    },
    {
      id: 'acmesh',
      code: [
        '# Save the key file of the previous tab, for example as /etc/ucm-tsig.key',
        `export NSUPDATE_SERVER="${host}"`,
        `export NSUPDATE_SERVER_PORT="${port}"`,
        'export NSUPDATE_KEY="/etc/ucm-tsig.key"',
        '# export NSUPDATE_ZONE="example.com"',
        `acme.sh --issue --dns dns_nsupdate --server ${directoryUrl} -d ${domain} --dnssleep 30`,
        '',
      ].join('\n'),
      noteKeys: ['noteAcmesh'],
    },
    {
      id: 'certbot',
      code: [
        '# /etc/letsencrypt/rfc2136.ini (chmod 600)',
        `dns_rfc2136_server = ${certbotServer}`,
        `dns_rfc2136_port = ${port}`,
        `dns_rfc2136_name = ${keyName}`,
        `dns_rfc2136_secret = ${secret}`,
        `dns_rfc2136_algorithm = ${algorithm.toUpperCase()}`,
        '',
        '# Command',
        `certbot certonly --server ${directoryUrl} --dns-rfc2136 \\`,
        `  --dns-rfc2136-credentials /etc/letsencrypt/rfc2136.ini -d ${domain}`,
        '',
      ].join('\n'),
      noteKeys: ['noteCertbot'],
    },
    {
      id: 'lego',
      code: [
        `export DNSUPDATE_NAMESERVER="${host}:${port}"`,
        `export DNSUPDATE_TSIG_KEY="${keyName}"`,
        `export DNSUPDATE_TSIG_SECRET="${secret}"`,
        `export DNSUPDATE_TSIG_ALGORITHM="${algorithm}."`,
        `lego --server ${directoryUrl} --email ${email} --accept-tos \\`,
        `  --dns rfc2136 --dns.propagation-wait 30s -d ${domain} run`,
        '',
      ].join('\n'),
      noteKeys: ['noteLego'],
    },
    {
      id: 'certmanager',
      code: certManager,
      unsupported: !cmAlgorithm,
      noteKeys: cmAlgorithm ? ['noteCertManagerZone'] : ['noteCertManagerSha384', 'noteCertManagerZone'],
    },
    {
      id: 'winacme',
      code: [
        '# Add your usual target options (for example the host name)',
        `wacs.exe --baseuri ${directoryUrl} --accepttos --emailaddress ${email} \``,
        '  --validationmode dns-01 --validation rfc2136 `',
        `  --serverhost ${host} \``,
        `  --tsigkeyname ${keyName} \``,
        `  --tsigkeysecret ${secret} \``,
        `  --tsigkeyalgorithm ${winAcmeAlgorithm(algorithm)}`,
        '',
      ].join('\n'),
      noteKeys: algorithm === 'hmac-sha384' ? ['noteWinAcmePort', 'noteWinAcmeSha384'] : ['noteWinAcmePort'],
    },
    {
      id: 'poshacme',
      code: [
        `Set-PAServer ${directoryUrl}`,
        '$pluginArgs = @{',
        `  DDNSNameserver = '${host}'`,
        `  DDNSPort       = '${port}'`,
        `  DDNSKeyName    = '${keyName}'`,
        `  DDNSKeyType    = '${algorithm}'`,
        `  DDNSKeyValue   = (ConvertTo-SecureString '${secret}' -AsPlainText -Force)`,
        '}',
        `New-PACertificate ${domain} -Plugin RFC2136 -PluginArgs $pluginArgs -DnsSleep 30`,
        '',
      ].join('\n'),
      noteKeys: ['notePoshNameserver'],
    },
  ]
}
