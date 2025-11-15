# Fix OAuth Authentication Issue

**Date**: 2025-11-01  
**Issue**: Chainlit bypassed OAuth login and went straight to `on_chat_start` with `user=None`  
**Status**: ✅ FIXED

## Problem

Khi truy cập `http://localhost:8501`, Chainlit không hiển thị màn hình login OAuth mà chạy thẳng vào `on_chat_start()` với `user=None`, gây ra lỗi:

```
2025-11-01 16:12:44.048 | INFO | chainlit.py:on_chat_end:128 - Chat ended: user=None, thread=None
```

## Root Cause

1. **Missing `require_login = true`** trong config.toml
2. **Missing OAuth callback handler** `@cl.oauth_callback` trong chainlit.py
3. OAuth được cấu hình nhưng không được enforce

## Solution

### 1. Enable Required Login

**File**: `frontend/.chainlit/config.toml`

```toml
[project.auth]
enable_password_auth = false
require_login = true  # ← Added this line
```

### 2. Add OAuth Callback Handler

**File**: `frontend/chainlit.py`

```python
@cl.oauth_callback
def oauth_callback(
    provider_id: str,
    token: str,
    raw_user_data: dict,
    default_user: cl.User,
) -> Optional[cl.User]:
    """
    OAuth callback handler for Google and GitHub providers.
    """
    logger.info(f"OAuth callback: provider={provider_id}, user_data={raw_user_data}")
    
    # Extract user information based on provider
    if provider_id == "google":
        user_id = raw_user_data.get("id")
        email = raw_user_data.get("email")
        name = raw_user_data.get("name", email)
        picture = raw_user_data.get("picture")
    elif provider_id == "github":
        user_id = raw_user_data.get("id")
        email = raw_user_data.get("email")
        name = raw_user_data.get("name") or raw_user_data.get("login", email)
        picture = raw_user_data.get("avatar_url")
    else:
        return None
    
    # Create identifier for backend
    identifier = f"{provider_id}:{user_id}"
    
    # Create Chainlit user object
    return cl.User(
        identifier=identifier,
        metadata={
            "provider": provider_id,
            "email": email,
            "name": name,
            "picture": picture,
            "raw_user_data": raw_user_data,
        }
    )
```

### 3. Update on_chat_start to Use Authenticated User

**File**: `frontend/chainlit.py`

```python
@cl.on_chat_start
async def on_chat_start():
    # Get authenticated user from Chainlit
    user = cl.user_session.get("user")

    if not user:
        # This should not happen if require_login = true
        logger.error("User not authenticated in on_chat_start")
        await cl.Message(
            content="❌ Authentication required. Please log in to continue."
        ).send()
        return

    # Get user identifier from OAuth callback
    user_identifier = user.identifier  # ← Changed from user.get("identifier")
    user_name = user.metadata.get("name", "User")  # ← Extract name from metadata
    
    logger.info(f"User authenticated: {user_identifier} ({user_name})")
    
    # ... rest of the code
```

## How It Works Now

### User Flow:

1. **User visits** `http://localhost:8501`
2. **Chainlit checks** `require_login = true`
3. **Shows login page** with OAuth buttons:
   - Sign in with Google
   - Sign in with GitHub
4. **User clicks** OAuth button
5. **Redirects to** OAuth provider (Google/GitHub)
6. **User authorizes** application
7. **OAuth provider redirects back** to Chainlit with auth code
8. **Chainlit calls** `oauth_callback()` function
9. **oauth_callback** creates `cl.User` object with:
   - `identifier`: `"google:123456"` or `"github:789012"`
   - `metadata`: email, name, picture, etc.
10. **User stored** in session
11. **on_chat_start** called with authenticated user
12. **Welcome message** displays with user name

### User Identifier Format:

- Google: `google:123456789`
- GitHub: `github:987654321`

This format allows backend to:
- Identify OAuth provider
- Link to provider user ID
- Store in database uniquely

## Testing

### Before Fix:

```bash
$ chainlit run chainlit.py --host 0.0.0.0 --port 8501

# Open http://localhost:8501
# ❌ No login page
# ❌ Direct to chat with user=None
# ❌ Error: Chat ended: user=None, thread=None
```

### After Fix:

```bash
$ chainlit run chainlit.py --host 0.0.0.0 --port 8501

# Open http://localhost:8501
# ✅ Shows login page
# ✅ Click "Sign in with Google"
# ✅ Authorize application
# ✅ Redirect back to Chainlit
# ✅ Chat started: user=google:123456 (John Doe)
# ✅ Welcome message: "Xin chào John Doe!"
```

## OAuth Setup Required

**IMPORTANT**: OAuth credentials phải được cấu hình trong `.env`:

```bash
# Google OAuth (get from https://console.cloud.google.com/)
GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxx

# GitHub OAuth (get from https://github.com/settings/developers)
GITHUB_CLIENT_ID=Iv1.xxxxx
GITHUB_CLIENT_SECRET=xxxxx

# Generate random secret
CHAINLIT_AUTH_SECRET=$(openssl rand -hex 32)
```

**Redirect URIs** phải được cấu hình trong OAuth provider:

- Google: `http://localhost:8501/auth/oauth/google/callback`
- GitHub: `http://localhost:8501/auth/oauth/github/callback`

See `OAUTH_SETUP_GUIDE.md` for detailed setup instructions.

## Development Mode (No OAuth)

Nếu muốn skip OAuth cho development:

```toml
[project.auth]
require_login = false  # ← Change to false
```

**⚠️ WARNING**: Chỉ dùng cho development! KHÔNG dùng cho production!

## Files Changed

1. `frontend/.chainlit/config.toml` - Added `require_login = true`
2. `frontend/chainlit.py` - Added `@cl.oauth_callback` handler
3. `frontend/chainlit.py` - Updated `on_chat_start` to use authenticated user
4. `frontend/OAUTH_SETUP_GUIDE.md` - Created setup guide

## Verification

### Check OAuth Callback:

```bash
# Run Chainlit with debug logging
chainlit run chainlit.py --host 0.0.0.0 --port 8501 --debug

# Login with Google
# Should see in logs:
# INFO | chainlit.py:oauth_callback:XX - OAuth callback: provider=google, user_data={...}
# INFO | chainlit.py:on_chat_start:XX - User authenticated: google:123456 (John Doe)
```

### Check Database:

```sql
-- After login, user should be created in database
SELECT * FROM users WHERE identifier LIKE 'google:%' OR identifier LIKE 'github:%';

-- Should return user record with OAuth identifier
```

## Summary

✅ **Fixed**: OAuth authentication now works correctly  
✅ **Login page**: Shows before accessing chat  
✅ **User session**: Properly authenticated with OAuth provider  
✅ **User identifier**: Format `provider:user_id` for backend integration  
✅ **Welcome message**: Displays user name from OAuth data  

**Result**: Users must authenticate before accessing chat interface!
