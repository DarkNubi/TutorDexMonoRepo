/**
 * Error Reporting Module
 * 
 * Integrates Sentry for production error reporting while maintaining
 * console logging for development.
 * 
 * Usage:
 *   import { reportError, setUserContext } from './errorReporter.js';
 * 
 *   try {
 *     await riskyOperation();
 *   } catch (error) {
 *     reportError(error, { context: 'loadAssignments', filters });
 *     showErrorMessage('Failed to load. Please try again.');
 *   }
 */

import * as Sentry from "@sentry/browser";

// Initialize Sentry only in production with DSN configured
const dsn = import.meta.env.VITE_SENTRY_DSN;
const environment = import.meta.env.VITE_SENTRY_ENVIRONMENT || "production";
const isProduction = import.meta.env.PROD;
const sentryEnabled = isProduction && dsn;

if (sentryEnabled) {
  try {
    Sentry.init({
      dsn: dsn,
      environment: environment,
      
      // Performance Monitoring
      integrations: [
        new Sentry.BrowserTracing({
          // Trace navigation and page loads
          tracePropagationTargets: ["localhost", /^\//],
        }),
      ],
      
      // Capture 10% of transactions for performance monitoring
      tracesSampleRate: 0.1,
      
      // Capture unhandled promise rejections
      beforeSend(event, hint) {
        // Filter out known non-critical errors
        if (event.exception) {
          const exceptionValue = event.exception.values?.[0]?.value || "";
          
          // Ignore network errors that are user-initiated (e.g., navigation away)
          if (exceptionValue.includes("NetworkError") || exceptionValue.includes("Failed to fetch")) {
            // Still log but don't send to Sentry
            console.warn("Network error (not sent to Sentry):", exceptionValue);
            return null;
          }
        }
        
        return event;
      },
      
      // Don't log personal data
      beforeBreadcrumb(breadcrumb) {
        // Redact URLs with sensitive query parameters
        if (breadcrumb.category === "xhr" || breadcrumb.category === "fetch") {
          if (breadcrumb.data?.url) {
            const url = new URL(breadcrumb.data.url, window.location.origin);
            // Remove sensitive query params if any
            url.searchParams.delete("token");
            url.searchParams.delete("key");
            breadcrumb.data.url = url.toString();
          }
        }
        return breadcrumb;
      },
    });
    
    console.log(`✓ Sentry initialized (${environment})`);
  } catch (error) {
    console.error("Failed to initialize Sentry:", error);
  }
}

/**
 * Report an error to Sentry (production) or console (development)
 * 
 * @param {Error} error - The error object to report
 * @param {Object} context - Additional context (e.g., {context: 'loadAssignments', filters: {...}})
 */
export function reportError(error, context = {}) {
  if (sentryEnabled) {
    Sentry.captureException(error, {
      extra: context,
      tags: {
        source: context.context || "unknown",
      },
    });
  }
  
  // Always log to console for visibility
  if (!isProduction || !sentryEnabled) {
    console.error("Error:", error, context);
  }
}

/**
 * Report a message (non-error) to Sentry
 * 
 * @param {string} message - The message to report
 * @param {string} level - Severity level: 'info', 'warning', 'error'
 * @param {Object} context - Additional context
 */
export function reportMessage(message, level = "info", context = {}) {
  if (sentryEnabled) {
    Sentry.captureMessage(message, {
      level: level,
      extra: context,
    });
  }
  
  if (!isProduction || !sentryEnabled) {
    console.log(`[${level.toUpperCase()}]`, message, context);
  }
}

/**
 * Set user context for error tracking
 * 
 * @param {string} uid - Firebase user ID
 * @param {Object} attributes - Additional user attributes (e.g., {email, plan})
 */
export function setUserContext(uid, attributes = {}) {
  if (sentryEnabled) {
    Sentry.setUser({
      id: uid,
      ...attributes,
    });
  }
  
  if (!isProduction) {
    console.log("User context set:", { uid, ...attributes });
  }
}

/**
 * Clear user context (call on logout)
 */
export function clearUserContext() {
  if (sentryEnabled) {
    Sentry.setUser(null);
  }
  
  if (!isProduction) {
    console.log("User context cleared");
  }
}

/**
 * Add breadcrumb for debugging context
 * 
 * @param {string} message - Breadcrumb message
 * @param {Object} data - Additional data
 * @param {string} category - Category (e.g., 'navigation', 'api', 'ui')
 */
export function addBreadcrumb(message, data = {}, category = "custom") {
  if (sentryEnabled) {
    Sentry.addBreadcrumb({
      message,
      category,
      data,
      level: "info",
    });
  }
  
  if (!isProduction) {
    console.log(`[Breadcrumb: ${category}]`, message, data);
  }
}

/**
 * Wrap an async function with error reporting
 * 
 * @param {Function} fn - Async function to wrap
 * @param {Object} context - Context to include in error reports
 * @returns {Function} Wrapped function
 */
export function withErrorReporting(fn, context = {}) {
  return async (...args) => {
    try {
      return await fn(...args);
    } catch (error) {
      reportError(error, { ...context, args });
      throw error; // Re-throw for caller to handle
    }
  };
}

/**
 * Check if Sentry is enabled
 * 
 * @returns {boolean}
 */
export function isSentryEnabled() {
  return sentryEnabled;
}

// Export Sentry for advanced usage if needed
export { Sentry };
