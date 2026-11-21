/** Renders a certificate in the Certificates zone dock body (CertificateBody), loaded by its id. */
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { CertificateBody } from '../pages/certificates/inspector/CertificateBody'

export function renderCertificateBody(id, { section = 'overview', onSection = () => {} } = {}) {
  const entry = { key: `certificate:${id}`, type: 'certificate', entityId: id, data: null }
  return render(
    <MemoryRouter>
      <CertificateBody entry={entry} onOpenCa={() => {}} section={section} onSection={onSection} />
    </MemoryRouter>,
  )
}
