import { UpdateChecker } from '../../components/UpdateChecker'
import AutoUpdateSettings from './AutoUpdateSettings'

export default function UpdatesSection() {
  return (
    <>
      <UpdateChecker />
      <AutoUpdateSettings />
    </>
  )
}
