import logging
import re
from models.msca import MicrosoftCA
from .connection import MicrosoftCAConnectionMixin

logger = logging.getLogger(__name__)


class MicrosoftCATemplatesMixin:

    @staticmethod
    def _get_templates(client):
        """Fetch available certificate templates by scraping certrqxt.asp."""
        url = f"https://{client.server}/certsrv/certrqxt.asp"
        try:
            response = client.session.get(url, timeout=client.timeout)
            response.raise_for_status()
            html = response.text
            raw_values = re.findall(
                r'<Option\s+Value="([^"]+)"',
                html,
                re.IGNORECASE
            )
            seen = set()
            unique = []
            for raw in raw_values:
                if ';' in raw:
                    parts = raw.split(';')
                    name = parts[1] if len(parts) > 1 else parts[0]
                else:
                    name = raw
                name = name.strip()
                if name and name not in seen:
                    seen.add(name)
                    unique.append(name)
            return unique
        except Exception as e:
            logger.warning(f"Failed to scrape templates from certrqxt.asp: {e}")
            raise

    @staticmethod
    def list_templates(msca_id):
        msca = MicrosoftCA.query.get(msca_id)
        if not msca:
            raise ValueError('Connection not found')

        client = None
        try:
            client = MicrosoftCAConnectionMixin._get_client(msca)
            templates = MicrosoftCATemplatesMixin._get_templates(client)
            return sorted(templates) if templates else []
        except Exception as e:
            logger.error(f"Failed to list templates for '{msca.name}': {e}")
            raise
        finally:
            if client:
                MicrosoftCAConnectionMixin._cleanup_client(client)
