"""
OPNsense connection mixin — session setup and config.xml retrieval.
"""
import re
import logging
from typing import Optional

from utils.safe_requests import create_session

logger = logging.getLogger(__name__)


class ConnectionMixin:
    """Handles connecting to OPNsense and downloading config.xml."""

    def connect(self) -> bool:
        """
        Test connection to OPNsense instance.

        Returns:
            True if connection successful.
        """
        try:
            self.session = create_session(verify_ssl=self.verify_ssl)

            logger.debug(f"OPNsense connect: Trying {self.base_url} (API mode: {self.use_api})")

            if self.use_api:
                response = self.session.get(
                    f"{self.base_url}/api/core/backup/providers",
                    auth=(self.api_key, self.api_secret),
                    timeout=10
                )
                logger.debug(f"OPNsense API test: Got status {response.status_code}")
                return response.status_code == 200
            else:
                response = self.session.get(
                    f"{self.base_url}/",
                    auth=(self.username, self.password),
                    timeout=10
                )
                logger.debug(f"OPNsense web test: Got status {response.status_code}")
                return response.status_code == 200

        except Exception as e:
            logger.error(f"OPNsense connect failed: {type(e).__name__}: {e}")
            return False

    def get_config_xml(self) -> Optional[str]:
        """
        Retrieve OPNsense config.xml.

        Uses REST API if api_key/secret provided, otherwise falls back to
        web scraping with CSRF handling.

        Returns:
            XML string or None if failed.
        """
        if self.use_api:
            return self._get_config_xml_api()
        else:
            return self._get_config_xml_web()

    def _get_config_xml_api(self) -> Optional[str]:
        """
        Retrieve config.xml using REST API.
        Endpoint: GET /api/core/backup/download/this

        Returns:
            XML string or None if failed.
        """
        try:
            logger.debug("get_config_xml_api: Downloading via REST API...")

            response = self.session.get(
                f"{self.base_url}/api/core/backup/download/this",
                auth=(self.api_key, self.api_secret),
                timeout=60
            )

            logger.debug(
                f"get_config_xml_api: Status {response.status_code}, "
                f"Size: {len(response.content)} bytes"
            )

            if response.status_code == 200:
                content = response.text

                if '<?xml' in content[:100]:
                    if '<opnsense>' in content or '<pfsense>' in content:
                        logger.debug("get_config_xml_api: Successfully retrieved config.xml via REST API")
                        return content
                    else:
                        logger.debug("get_config_xml_api: XML found but not OPNsense format")
                else:
                    logger.debug(f"get_config_xml_api: Response is not XML. Content starts: {content[:200]}")
            else:
                logger.debug(f"get_config_xml_api: Request failed with status {response.status_code}")
                if response.status_code == 401:
                    logger.debug("get_config_xml_api: Authentication failed - check API key/secret")

            return None

        except Exception as e:
            logger.error(f"get_config_xml_api failed: {type(e).__name__}: {e}")
            return None

    def _get_config_xml_web(self) -> Optional[str]:
        """
        Retrieve OPNsense config.xml with web scraping and CSRF handling.
        OPNsense uses X-CSRFToken header instead of form fields.

        Returns:
            XML string or None if failed.
        """
        try:
            # Step 1: GET login page to obtain CSRF token
            logger.debug("get_config_xml_web: Step 1 - Getting login page for CSRF token...")

            login_page_response = self.session.get(
                f"{self.base_url}/",
                timeout=30
            )

            if login_page_response.status_code != 200:
                logger.debug(f"get_config_xml_web: Failed to get login page: {login_page_response.status_code}")
                return None

            # Extract CSRF token from JavaScript
            # OPNsense embeds it in: xhr.setRequestHeader("X-CSRFToken", "TOKEN_HERE");
            csrf_pattern = r'X-CSRFToken["\']\s*,\s*["\']([^"\']+)["\']'
            csrf_match = re.search(csrf_pattern, login_page_response.text)

            if not csrf_match:
                logger.debug(
                    f"get_config_xml_web: Could not find X-CSRFToken in page. "
                    f"Content starts: {login_page_response.text[:1000]}"
                )
                return None

            csrf_token = csrf_match.group(1)
            logger.debug(f"get_config_xml_web: Found X-CSRFToken: {csrf_token}")

            # Step 2: POST login with X-CSRFToken header
            logger.debug("get_config_xml_web: Step 2 - Logging in with X-CSRFToken header...")

            login_response = self.session.post(
                f"{self.base_url}/",
                data={
                    'usernamefld': self.username,
                    'passwordfld': self.password,
                    'login': 'Login'
                },
                headers={'X-CSRFToken': csrf_token},
                timeout=30,
                allow_redirects=True
            )

            logger.debug(f"get_config_xml_web: Login response status: {login_response.status_code}")

            if login_response.status_code == 403:
                logger.debug("get_config_xml_web: Login failed - 403 Forbidden")
                return None

            # Step 3: GET backup page to obtain new CSRF token
            logger.debug("get_config_xml_web: Step 3 - Getting backup page for new CSRF token...")

            backup_page_response = self.session.get(
                f"{self.base_url}/diag_backup.php",
                timeout=30
            )

            if backup_page_response.status_code != 200:
                logger.debug(f"get_config_xml_web: Failed to get backup page: {backup_page_response.status_code}")
                return None

            # Extract new CSRF token from backup page
            csrf_match = re.search(csrf_pattern, backup_page_response.text)

            if not csrf_match:
                logger.debug("get_config_xml_web: Could not find new CSRF token, reusing old one")
            else:
                csrf_token = csrf_match.group(1)
                logger.debug(f"get_config_xml_web: Found new X-CSRFToken: {csrf_token}")

            # Step 4: POST download request with X-CSRFToken header
            logger.debug("get_config_xml_web: Step 4 - Downloading config with X-CSRFToken header...")

            backup_response = self.session.post(
                f"{self.base_url}/diag_backup.php",
                data={
                    'download': 'download',
                    'donotbackuprrd': 'yes'
                },
                headers={'X-CSRFToken': csrf_token},
                timeout=60
            )

            logger.debug(
                f"get_config_xml_web: Backup download status: {backup_response.status_code}, "
                f"Content length: {len(backup_response.content)}"
            )

            # If first attempt returns HTML, try alternative method
            if backup_response.status_code == 200 and '<!doctype html>' in backup_response.text.lower()[:100]:
                logger.debug("get_config_xml_web: First attempt returned HTML, trying alternative method...")

                backup_response = self.session.post(
                    f"{self.base_url}/diag_backup.php",
                    data={
                        'action': 'download',
                        'donotbackuprrd': '1'
                    },
                    headers={'X-CSRFToken': csrf_token},
                    timeout=60
                )

                logger.debug(f"get_config_xml_web: Alternative method status: {backup_response.status_code}")

            # If still HTML, try method 3: GET with query params
            if backup_response.status_code == 200 and '<!doctype html>' in backup_response.text.lower()[:100]:
                logger.debug("get_config_xml_web: Still HTML, trying GET method...")

                backup_response = self.session.get(
                    f"{self.base_url}/diag_backup.php?download=download&donotbackuprrd=yes",
                    headers={'X-CSRFToken': csrf_token},
                    timeout=60
                )

                logger.debug(f"get_config_xml_web: GET method status: {backup_response.status_code}")

            if backup_response.status_code == 200:
                content = backup_response.text

                if '<?xml' in content[:100]:
                    logger.debug("get_config_xml_web: Valid XML found!")

                    if '<opnsense>' in content or '<pfsense>' in content:
                        logger.debug(f"get_config_xml_web: OPNsense/pfSense config confirmed! Size: {len(content)} bytes")
                        return content
                    else:
                        logger.debug("get_config_xml_web: XML found but not OPNsense/pfSense format")
                else:
                    logger.debug(f"get_config_xml_web: Response is not XML. Content starts: {content[:200]}")
            else:
                logger.debug(f"get_config_xml_web: Backup download failed with status {backup_response.status_code}")

            return None

        except Exception as e:
            logger.error(f"get_config_xml_web: Exception occurred: {type(e).__name__}: {e}", exc_info=True)
            return None
