/**
 * DNS Provider Icons - Official brand logos via Simple Icons + custom SVGs
 * Used by the ProviderTypeGrid in ACMEPage
 */
import {
  SiCloudflare, SiDigitalocean, SiOvh, SiHetzner, SiGandi, SiScaleway,
  SiVultr, SiGodaddy, SiNamecheap, SiVercel, SiPorkbun, SiBunnydotnet,
  SiIonos, SiNetcup, SiInfomaniak, SiAlwaysdata, SiAkamai
} from '@icons-pack/react-simple-icons'

// Custom SVG icons for providers not in Simple Icons
const AwsIcon = ({ size = 20 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor">
    <path d="M6.763 10.036c0 .296.032.535.088.71.064.176.144.368.256.576.04.063.056.127.056.183 0 .08-.048.16-.152.24l-.503.335a.383.383 0 0 1-.208.072c-.08 0-.16-.04-.239-.112a2.47 2.47 0 0 1-.287-.374 6.18 6.18 0 0 1-.248-.47c-.622.734-1.405 1.101-2.347 1.101-.67 0-1.205-.191-1.596-.574-.391-.384-.59-.894-.59-1.533 0-.678.239-1.23.726-1.644.487-.415 1.133-.623 1.955-.623.272 0 .551.024.846.064.296.04.6.104.918.176v-.583c0-.607-.127-1.03-.375-1.277-.255-.248-.686-.367-1.3-.367-.28 0-.568.032-.863.104-.296.072-.584.16-.863.272a2.287 2.287 0 0 1-.28.104.488.488 0 0 1-.127.023c-.112 0-.168-.08-.168-.247v-.391c0-.128.016-.224.056-.28a.597.597 0 0 1 .224-.167c.279-.144.614-.264 1.005-.36a4.84 4.84 0 0 1 1.246-.151c.95 0 1.644.216 2.091.647.439.43.662 1.085.662 1.963v2.586zm-3.24 1.214c.263 0 .534-.048.822-.144.287-.096.543-.271.758-.51.128-.152.224-.32.272-.512.047-.191.08-.423.08-.694v-.335a6.66 6.66 0 0 0-.735-.136 6.02 6.02 0 0 0-.75-.048c-.535 0-.926.104-1.19.32-.263.215-.39.518-.39.917 0 .375.095.655.295.846.191.2.47.296.838.296zm6.41.862c-.144 0-.24-.024-.304-.08-.064-.048-.12-.16-.168-.311L7.586 5.55a1.398 1.398 0 0 1-.072-.32c0-.128.064-.2.191-.2h.783c.151 0 .255.025.31.08.065.048.113.16.16.312l1.342 5.284 1.245-5.284c.04-.16.088-.264.151-.312a.549.549 0 0 1 .32-.08h.638c.152 0 .256.025.32.08.063.048.12.16.151.312l1.261 5.348 1.381-5.348c.048-.16.104-.264.16-.312a.52.52 0 0 1 .311-.08h.743c.128 0 .2.064.2.2 0 .04-.009.08-.017.128a1.137 1.137 0 0 1-.056.2l-1.923 6.17c-.048.16-.104.264-.168.312a.549.549 0 0 1-.32.08h-.687c-.152 0-.256-.024-.32-.08-.063-.056-.12-.16-.15-.32l-1.238-5.148-1.23 5.14c-.04.16-.087.264-.15.32-.065.056-.177.08-.32.08zm10.256.215c-.415 0-.83-.048-1.229-.143-.399-.096-.71-.2-.918-.32-.128-.071-.216-.151-.248-.224a.585.585 0 0 1-.048-.224v-.407c0-.167.064-.247.183-.247.048 0 .096.008.144.024.048.016.12.048.2.08.271.12.566.215.878.279.32.064.63.096.95.096.502 0 .894-.088 1.165-.264a.86.86 0 0 0 .415-.758.777.777 0 0 0-.215-.559c-.144-.151-.415-.287-.806-.415l-1.157-.36c-.583-.183-1.014-.454-1.277-.813a1.902 1.902 0 0 1-.4-1.158c0-.335.073-.63.216-.886.144-.255.335-.479.575-.654.24-.184.51-.32.83-.415.32-.096.655-.136 1.006-.136.175 0 .359.008.535.032.183.024.35.056.518.088.16.04.312.08.455.127.144.048.256.096.336.144a.69.69 0 0 1 .24.2.43.43 0 0 1 .071.263v.375c0 .168-.064.256-.184.256a.83.83 0 0 1-.303-.096 3.652 3.652 0 0 0-1.532-.311c-.455 0-.815.072-1.062.223-.248.152-.375.383-.375.694 0 .224.08.416.24.567.16.152.454.304.87.44l1.133.358c.574.184.99.44 1.237.767.247.327.367.702.367 1.117 0 .343-.072.655-.207.926-.144.272-.336.511-.583.703-.248.2-.543.343-.886.447-.36.112-.735.168-1.142.168z" />
    <path d="M21.698 16.793c-2.812 2.076-6.89 3.18-10.399 3.18-4.918 0-9.347-1.82-12.698-4.844-.263-.239-.032-.567.287-.383 3.616 2.104 8.09 3.372 12.706 3.372 3.117 0 6.538-.646 9.69-1.987.479-.2.878.311.414.662z" />
    <path d="M22.82 15.502c-.36-.462-2.379-.224-3.291-.112-.271.032-.311-.208-.064-.383 1.613-1.133 4.26-.806 4.57-.424.31.39-.088 3.069-1.596 4.347-.232.2-.455.096-.351-.168.343-.854 1.093-2.798.732-3.26z" />
  </svg>
)

const AzureIcon = ({ size = 20 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor">
    <path d="M5.483 21.3H14.3L8.26 9.758l3.5-7.602L1.197 21.3zm17.12 0H10.63l5.747-4.87L19.6 9.642z" />
  </svg>
)

const GoogleCloudIcon = ({ size = 20 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor">
    <path d="M12.19 2.38a9.344 9.344 0 0 0-9.234 6.893c.053-.02-.055.013 0 0-3.875 2.551-3.922 8.11-.247 10.941l.006-.007-.007.003a6.542 6.542 0 0 0 3.624 1.098h12.09c3.33-.02 6.078-2.594 6.32-5.898.308-4.223-3.218-7.893-7.378-7.683a9.37 9.37 0 0 0-5.174-5.347zM12.19 4.38c1.64 0 3.183.614 4.382 1.703l-.182.19-1.72 1.69-.134.14-.166-.11a5.276 5.276 0 0 0-2.932-.886 5.326 5.326 0 0 0-4.836 3.082l-.084.17-.177-.058-2.124-.695-.093-.03.063-.12a8.314 8.314 0 0 1 8.003-5.076zm6.616 4.476a6.26 6.26 0 0 1 5.018 5.814c-.127 2.627-2.36 4.718-5.008 4.726H6.332a4.505 4.505 0 0 1-2.504-.76 4.558 4.558 0 0 1-.458-7.063l.165-.136.186.114c.66.403 1.399.699 2.173.862l.246.052-.063.242a5.294 5.294 0 0 0-.107 1.06 5.327 5.327 0 0 0 5.326 5.328 5.33 5.33 0 0 0 4.29-2.178l.126-.168.18.096a8.06 8.06 0 0 0 1.65.537l.25.05-.063.246a8.384 8.384 0 0 1-.09.427c-.025.09-.07.22-.084.236l-.003.004c1.312-.266 2.506-.965 3.386-1.983a6.09 6.09 0 0 0 1.397-4.04c-.06-1.29-.553-2.448-1.28-3.382z" />
  </svg>
)

const DreamhostIcon = ({ size = 20 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor">
    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 15H8v-2h3v2zm5-4H8v-2h8v2zm0-4H8V7h8v2z" />
  </svg>
)

// Text-based logos for providers without official icons
const TextLogo = ({ text, size = 20 }) => (
  <span style={{ fontSize: size * 0.45, fontWeight: 700, lineHeight: 1, letterSpacing: '-0.02em' }}
    className="font-mono select-none">{text}</span>
)

// Provider icon component mapping
const PROVIDER_ICONS = {
  // Simple Icons (official brand SVGs)
  cloudflare:   { Icon: SiCloudflare,   color: '#F38020' },
  route53:      { Icon: AwsIcon,        color: '#FF9900' },
  azure:        { Icon: AzureIcon,      color: '#0078D4' },
  gcloud:       { Icon: GoogleCloudIcon, color: '#4285F4' },
  digitalocean: { Icon: SiDigitalocean, color: '#0080FF' },
  ovh:          { Icon: SiOvh,          color: '#123F6D' },
  hetzner:      { Icon: SiHetzner,      color: '#D50C2D' },
  gandi:        { Icon: SiGandi,        color: '#6640FE' },
  scaleway:     { Icon: SiScaleway,     color: '#4F0599' },
  vultr:        { Icon: SiVultr,        color: '#007BFC' },
  godaddy:      { Icon: SiGodaddy,      color: '#1BDBDB' },
  namecheap:    { Icon: SiNamecheap,    color: '#DE3723' },
  vercel:       { Icon: SiVercel,       color: '#000000' },
  porkbun:      { Icon: SiPorkbun,      color: '#EF7878' },
  bunny:        { Icon: SiBunnydotnet,  color: '#FFAA49' },
  ionos:        { Icon: SiIonos,        color: '#003D8F' },
  netcup:       { Icon: SiNetcup,       color: '#056473' },
  infomaniak:   { Icon: SiInfomaniak,   color: '#0098FF' },
  alwaysdata:   { Icon: SiAlwaysdata,   color: '#E9568E' },
  linode:       { Icon: SiAkamai,       color: '#0096D6' },
  dreamhost:    { Icon: DreamhostIcon,  color: '#0073EC' },
  
  // Text-based logos for providers without SVGs
  manual:       { text: '⚙️', color: '#6B7280' },
  dnsimple:     { text: 'DS',  color: '#1A8BB2' },
  dnsmadeeasy:  { text: 'DME', color: '#2EA553' },
  easydns:      { text: 'ez',  color: '#E8423B' },
  cloudns:      { text: 'CL',  color: '#2E7CBF' },
  dynu:         { text: 'DY',  color: '#1EAAAF' },
  desec:        { text: 'dS',  color: '#E2A62E' },
  duckdns:      { text: '🦆',  color: '#E0C331' },
  freedns:      { text: 'FD',  color: '#65A30D' },
  inwx:         { text: 'IX',  color: '#1C7D83' },
  bookmyname:   { text: 'BN',  color: '#5046E5' },
  domeneshop:   { text: 'DS',  color: '#CB2027' },
  corenetworks: { text: 'CN',  color: '#4B5563' },
  checkdomain:  { text: 'CD',  color: '#059669' },
}

/**
 * Renders a provider's icon
 * @param {string} type - Provider type key (e.g. 'cloudflare', 'route53')
 * @param {number} size - Icon size in pixels (default 20)
 */
export function ProviderIcon({ type, size = 20, className = '' }) {
  const provider = PROVIDER_ICONS[type]
  
  if (!provider) {
    return <span className={className} style={{ fontSize: size * 0.7 }}>🌐</span>
  }
  
  if (provider.Icon) {
    return <provider.Icon size={size} color="white" className={className} />
  }
  
  if (provider.text?.length <= 3 && !provider.text.match(/[\u{1F000}-\u{1FFFF}]/u)) {
    return <TextLogo text={provider.text} size={size} />
  }
  
  return <span style={{ fontSize: size * 0.7 }}>{provider.text}</span>
}

/**
 * Returns the brand color for a provider
 * @param {string} type - Provider type key
 * @returns {string} Hex color
 */
export function getProviderColor(type) {
  return PROVIDER_ICONS[type]?.color || '#6B7280'
}

export default PROVIDER_ICONS
