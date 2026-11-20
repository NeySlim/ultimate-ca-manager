// Panels of the work queue objects in the inspector, by inspector type (config.js)
import { ApprovalDetail } from '../../pages/approvals/ApprovalDetail'
import { KeyRecoveryDetail } from '../../pages/keyRecovery/KeyRecoveryDetail'
import { ReportDetail } from '../../pages/reports/ReportDetail'

export const QUEUE_DETAILS = {
  approval: ApprovalDetail,
  key_recovery: KeyRecoveryDetail,
  report: ReportDetail,
}
