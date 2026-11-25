/** Playwright's limit for one test (playwright.config.ts): a seed lock older than it has no living maker. */
export const TEST_TIMEOUT_MS = 60_000
/** What a test waits for a seed another worker is making: less than its own limit. */
export const SEED_WAIT_MS = 45_000
/** The restore route answers within its bounded wait (JOB_WAIT_SECONDS, 25 s): its report can come that late. */
export const RESTORE_ANSWER_MS = 40_000
