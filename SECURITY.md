# Security Policy for GinkAssistant

## Supported Versions

GinkAssistant is currently in active development. Security updates are prioritized for the main branch and the most recent stable releases to ensure API keys and user data remain protected.

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take the security of GinkAssistant very seriously. If you discover a security vulnerability, we appreciate your help in disclosing it to us in a responsible manner.

### How to report
**Please do not report security vulnerabilities via public GitHub issues.**

Instead, please send a detailed report to:
**[Insert Your Email Here]**

In your report, please include:
*   **Description:** A detailed summary of the vulnerability.
*   **Steps to Reproduce:** Proof-of-concept code, screenshots, or a clear list of steps.
*   **Impact:** What could happen if this vulnerability is exploited (e.g., API key theft, history access).

### Our Response Process
*   **Acknowledgment:** You will receive an acknowledgment of your report within **48 hours**.
*   **Investigation:** We will investigate the issue and may contact you for further details.
*   **Resolution:** If the vulnerability is accepted, we will work on a fix and provide an estimated timeline for the update. We request that you do not disclose the issue publicly until a patch is released.

## User Security Responsibilities

To keep your GinkAssistant environment secure, please follow these best practices:

1.  **Groq API Keys:** Do not hardcode your API keys in `worker.py`. Use environment variables or a secure `.env` file that is listed in your `.gitignore`.
2.  **App Passwords:** When using the Gmail OTP feature, always use a **Google App Password** rather than your primary account password.
3.  **Local History:** Be aware that chat history is stored locally. Ensure your computer's user account is password protected to prevent unauthorized access to your database.
