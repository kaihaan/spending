/**
 * Utility functions for handling promises in React components
 * Fixes @typescript-eslint/no-floating-promises and @typescript-eslint/no-misused-promises
 */

/**
 * Wraps an async function for use in event handlers
 * Prevents "Promise-returning function provided to attribute" errors
 *
 * @example
 * // Before (error):
 * <button onClick={handleDelete}>Delete</button>
 *
 * // After (fixed):
 * <button onClick={handleAsync(handleDelete)}>Delete</button>
 */
export function handleAsync<T extends unknown[]>(
  fn: (...args: T) => Promise<void>
): (...args: T) => void {
  return (...args: T) => {
    void fn(...args).catch((error) => {
      console.error('Unhandled async error:', error);
    });
  };
}

/**
 * Marks a promise as intentionally not awaited
 * Use when you want fire-and-forget behavior
 *
 * @example
 * // Before (error):
 * fetchData();
 *
 * // After (fixed):
 * fireAndForget(fetchData());
 */
export function fireAndForget(promise: Promise<unknown>): void {
  void promise.catch((error) => {
    console.error('Fire-and-forget promise failed:', error);
  });
}
