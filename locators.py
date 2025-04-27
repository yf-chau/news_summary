# locators.py

# Login Page
LOGIN_EMAIL_INPUT_SELECTOR = "input[type='email'][name='email']"
LOGIN_CONTINUE_BUTTON_SELECTOR = "role=button[name='Continue']"
LOGIN_PASSWORD_INPUT_SELECTOR = "input[type='password'][name='password']"
LOGIN_SIGN_IN_BUTTON_SELECTOR = "role=button[name='Sign in']"
LOGIN_ERROR_MESSAGE_SELECTOR = "div.error-message"

# Login Option
PASSWORD_LOGIN_LINK_SELECTOR = (
    "a.login-option.substack-login__login-option:has-text('Sign in with password')"
)

# Post-Login / Dashboard
DASHBOARD_INDICATOR_SELECTOR = "button:has-text('Dashboard')"
NEW_POST_BUTTON_SELECTOR = "button:has-text('New post')"
NEW_TEXT_POST_BUTTON_SELECTOR = "role=link[name='Text post']"

# Editor Page
POST_TITLE_INPUT_SELECTOR = "textarea[placeholder='Title']"
POST_CONTENT_EDITOR_SELECTOR = "div.tiptap.ProseMirror"
POST_CONTINUE_BUTTON_SELECTOR = (
    "button[data-testid='publish-button']:has-text('Continue')"
)

# Publish Page
SEND_BUTTON_SELECTOR = "button:has-text('Send to everyone now')"
