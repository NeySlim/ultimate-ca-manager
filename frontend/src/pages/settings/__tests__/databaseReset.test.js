import { describe, it, expect, vi } from 'vitest'
import { afterDatabaseReset } from '../databaseReset'

const t = (key, values) => (values ? `${key} ${JSON.stringify(values)}` : key)

function tools() {
  return { t, showConfirm: vi.fn().mockResolvedValue(true), showSuccess: vi.fn(), reload: vi.fn() }
}

describe('afterDatabaseReset', () => {
  it('shows where a generated password is and reloads only once acknowledged', async () => {
    const ui = tools()
    let acknowledge
    ui.showConfirm.mockReturnValue(new Promise(r => { acknowledge = r }))
    const done = afterDatabaseReset({ data: { password_generated: true, read_command: 'sudo cat /x/initial-admin-password' } }, ui)
    await Promise.resolve()
    expect(ui.showConfirm).toHaveBeenCalledTimes(1)
    const [message, options] = ui.showConfirm.mock.calls[0]
    expect(message).toContain('messages.success.database.resetGenerated')
    expect(message).toContain('sudo cat /x/initial-admin-password')
    expect(options.cancelText).toBeNull()
    expect(ui.reload).not.toHaveBeenCalled()
    acknowledge(true)
    await done
    expect(ui.reload).toHaveBeenCalledTimes(1)
    expect(ui.showSuccess).not.toHaveBeenCalled()
  })

  it('names the node holding the file in HA', async () => {
    const ui = tools()
    await afterDatabaseReset({ data: { password_generated: true, read_command: 'sudo cat /x/f', node: 'node-b' } }, ui)
    const [message] = ui.showConfirm.mock.calls[0]
    expect(message).toContain('messages.success.database.resetGeneratedOnNode')
    expect(message).toContain('node-b')
    expect(message).toContain('sudo cat /x/f')
  })

  it('keeps the short notice when the password was provided', async () => {
    vi.useFakeTimers()
    const ui = tools()
    await afterDatabaseReset({ data: { password_generated: false, read_command: null } }, ui)
    expect(ui.showConfirm).not.toHaveBeenCalled()
    expect(ui.showSuccess).toHaveBeenCalledWith('messages.success.database.reset')
    vi.advanceTimersByTime(2000)
    expect(ui.reload).toHaveBeenCalledTimes(1)
    vi.useRealTimers()
  })
})
