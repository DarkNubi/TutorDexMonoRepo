# Frontend Error Reporting with Sentry

This document describes the error reporting setup for the TutorDex website.

## Overview

The website now includes Sentry integration for production error reporting. This provides:

- **Automatic error capture**: Unhandled exceptions and promise rejections
- **User context**: Associate errors with Firebase UIDs
- **Breadcrumbs**: Track user actions leading to errors
- **Performance monitoring**: 10% sample rate for page load times
- **Development fallback**: Console logging when Sentry is not configured

## Setup

### 1. Install Dependencies

```bash
cd TutorDexWebsite
npm install @sentry/browser
```

### 2. Configure Sentry DSN

Create a `.env` file (or update existing):

```bash
# .env (for production)
VITE_SENTRY_DSN=https://your-sentry-dsn@sentry.io/your-project-id
VITE_SENTRY_ENVIRONMENT=production
```

**Note**: Sentry is only initialized in production builds (`import.meta.env.PROD === true`).

### 3. Get Your Sentry DSN

1. Sign up for free at [sentry.io](https://sentry.io)
2. Create a new project (select "Browser JavaScript")
3. Copy the DSN from project settings
4. Add to your `.env` file

## Usage

### Basic Error Reporting

```javascript
import { reportError } from './errorReporter.js';

try {
  await riskyOperation();
} catch (error) {
  reportError(error, { 
    context: 'loadAssignments',
    filters: currentFilters,
    userId: uid
  });
  showErrorMessage('Failed to load. Please try again.');
}
```

### Set User Context

```javascript
import { setUserContext, clearUserContext } from './errorReporter.js';

// When user logs in
const uid = await getCurrentUid();
setUserContext(uid, { email: user.email });

// When user logs out
clearUserContext();
```

### Add Breadcrumbs

```javascript
import { addBreadcrumb } from './errorReporter.js';

addBreadcrumb('Filter applied', { 
  level: 'Primary',
  subject: 'Maths' 
}, 'ui');
```

### Report Non-Error Messages

```javascript
import { reportMessage } from './errorReporter.js';

reportMessage('Unusual behavior detected', 'warning', {
  action: 'loadMore',
  totalLoaded: 150
});
```

## Integration Points

Error reporting is integrated at key points:

### 1. Assignments Page (`src/page-assignments.js`)

- **loadAssignments**: Reports errors loading assignment list
- **loadProfileContext**: Reports errors loading user profile
- User context set when authenticated

### 2. Profile Page (`src/page-profile.js`)

- **saveProfile**: Reports errors saving profile
- **generateLinkCode**: Reports errors generating Telegram link codes
- **getRecentMatchCounts**: Reports errors loading match statistics

### 3. Auth (`auth.js`)

- **logout**: Clears user context on sign out

## Error Filtering

The error reporter includes smart filtering:

### Ignored Errors

These errors are logged to console but NOT sent to Sentry:

- **Network errors during navigation**: User clicked away before request completed
- **Failed to fetch**: Often caused by user action, not bugs

### Redacted Data

Sensitive data is automatically removed:

- Query parameters: `token`, `key`
- User email (unless explicitly added to context)

## Development vs Production

### Development Mode

When `import.meta.env.PROD === false`:

- ✅ Errors logged to console
- ✅ Breadcrumbs logged to console
- ❌ No data sent to Sentry
- ❌ No network requests

### Production Mode

When `import.meta.env.PROD === true` AND `VITE_SENTRY_DSN` is set:

- ✅ Errors sent to Sentry
- ✅ Breadcrumbs tracked
- ✅ User context attached
- ✅ Performance monitoring (10% sample)

## Sentry Dashboard

### Viewing Errors

1. Go to sentry.io and log in
2. Select your project
3. Click "Issues" to see error reports
4. Each error shows:
   - Error message and stack trace
   - User context (Firebase UID)
   - Breadcrumbs (user actions before error)
   - Device/browser information
   - URL and query parameters

### Setting Up Alerts

1. Go to "Alerts" in Sentry
2. Create alert rule:
   - **Trigger**: Error count > threshold
   - **Action**: Email or Slack notification
3. Example: Alert if >10 errors in 1 hour

### Performance Monitoring

1. Go to "Performance" in Sentry
2. View page load times
3. Identify slow pages
4. Note: Only 10% of transactions are captured (configurable in `errorReporter.js`)

## Testing

### Test Error Reporting

1. Build for production:
   ```bash
   npm run build
   ```

2. Add this to any page temporarily:
   ```javascript
   // Test error
   setTimeout(() => {
     throw new Error('Test error for Sentry');
   }, 3000);
   ```

3. Open the production build
4. Check Sentry dashboard for the error

### Test in Development

Errors will only log to console:

```javascript
import { reportError } from './errorReporter.js';

reportError(new Error('Dev test error'), { 
  context: 'testing',
  note: 'This should only log to console in dev'
});
```

## Configuration Options

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_SENTRY_DSN` | No | Sentry project DSN (enables Sentry) |
| `VITE_SENTRY_ENVIRONMENT` | No | Environment name (default: "production") |

### Performance Tuning

Edit `src/errorReporter.js`:

```javascript
// Adjust sample rate (0.0 - 1.0)
tracesSampleRate: 0.1, // 10% of transactions

// Adjust filtering
beforeSend(event, hint) {
  // Add custom filtering logic
  return event;
}
```

## Privacy & Data Protection

### What is Sent to Sentry

- ✅ Error messages and stack traces
- ✅ Firebase UID (anonymized user identifier)
- ✅ URL and page context
- ✅ Browser and device type
- ✅ Custom context (filters, actions, etc.)

### What is NOT Sent

- ❌ User email (unless explicitly added)
- ❌ Passwords or credentials
- ❌ Sensitive query parameters (automatically redacted)
- ❌ Full assignment content

### GDPR Compliance

- Sentry supports data deletion requests
- User IDs are Firebase UIDs (not personally identifiable)
- Configure data retention in Sentry settings

## Troubleshooting

### Sentry Not Working

1. **Check DSN is set**:
   ```bash
   echo $VITE_SENTRY_DSN
   ```

2. **Check production mode**:
   ```javascript
   console.log(import.meta.env.PROD); // Should be true
   ```

3. **Check browser console**: Look for "✓ Sentry initialized"

4. **Check network tab**: Should see requests to `sentry.io`

### Errors Not Appearing in Sentry

- Errors might be filtered (check `beforeSend` in `errorReporter.js`)
- Network errors are intentionally not sent
- Check Sentry project DSN is correct
- Check Sentry project is active

### Too Many Errors

1. **Add rate limiting** in Sentry dashboard:
   - Settings → Data → Rate Limits

2. **Improve error filtering**:
   ```javascript
   beforeSend(event, hint) {
     // Filter out known non-critical errors
     if (event.message?.includes('Known warning')) {
       return null;
     }
     return event;
   }
   ```

## Cost Management

Sentry offers:

- **Free tier**: 5,000 errors/month, 10,000 transactions/month
- **Paid tiers**: Start at $26/month

To stay within free tier:

1. Use error filtering (already implemented)
2. Keep performance sampling at 10% or lower
3. Set up alerts for quota usage
4. Archive or delete resolved issues

## Future Enhancements

- [ ] Add session replay for visual debugging
- [ ] Integrate with backend error tracking
- [ ] Add custom tags for better categorization
- [ ] Set up release tracking (tag errors by deployment)
- [ ] Add source maps for minified production code

## Related Files

- `TutorDexWebsite/src/errorReporter.js` - Error reporting module
- `TutorDexWebsite/src/page-assignments.js` - Assignments page integration
- `TutorDexWebsite/src/page-profile.js` - Profile page integration
- `TutorDexWebsite/package.json` - Sentry dependency
- `docs/CODEBASE_QUALITY_AUDIT_2026-01.md` - Priority 6 details

## References

- [Sentry Browser SDK Documentation](https://docs.sentry.io/platforms/javascript/)
- [Sentry Performance Monitoring](https://docs.sentry.io/product/performance/)
- [Sentry Privacy Controls](https://docs.sentry.io/data-management/sensitive-data/)
