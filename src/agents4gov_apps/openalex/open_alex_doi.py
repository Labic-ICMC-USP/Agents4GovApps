import json

import requests
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        openalex_email: str = Field(
            default="",
            description="Email for OpenAlex polite pool (improves rate limits)",
        )

    def __init__(self):
        self.valves = self.Valves()

    def _clean_doi(self, doi: str) -> str:
        """
        Clean and normalize a DOI string by removing common prefixes.

        Args:
            doi: The DOI string to clean

        Returns:
            Cleaned DOI string without prefixes like 'doi:', 'https://doi.org/', etc.
        """
        doi_clean = doi.strip()

        if doi_clean.lower().startswith('doi:'):
            doi_clean = doi_clean[4:].strip()
        if doi_clean.startswith('https://doi.org/'):
            doi_clean = doi_clean.replace('https://doi.org/', '')
        if doi_clean.startswith('http://doi.org/'):
            doi_clean = doi_clean.replace('http://doi.org/', '')

        return doi_clean

    def get_openalex_metadata_by_doi(
        self,
        doi: str = Field(
            ...,
            description="The DOI (Digital Object Identifier) of the publication, e.g., '10.1371/journal.pone.0000000'"
        )
    ) -> str:
        """
        Retrieve essential metadata and impact indicators for a publication from OpenAlex.

        Returns a JSON string with structured publication metadata, citation indicators, and useful links.

        Args:
            doi: The DOI of the publication to query

        Returns:
            JSON string with structured publication data and impact metrics
        """

        doi_clean = self._clean_doi(doi)
        base_url = f"https://api.openalex.org/works/doi:{doi_clean}"
        params = {}
        if self.valves.openalex_email:
            params['mailto'] = self.valves.openalex_email

        try:
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            title = data.get('title', None)
            publication_year = data.get('publication_year', None)
            publication_date = data.get('publication_date', None)
            type_crossref = data.get('type_crossref', None)
            authors_list = data.get('authorships', [])
            authors = [
                author_info.get('author', {}).get('display_name')
                for author_info in authors_list
            ]
            primary_location = data.get('primary_location', {})
            source = primary_location.get('source', {}) or {}
            venue_name = source.get('display_name')
            cited_by_count = data.get('cited_by_count', 0)
            citation_normalized_percentile = data.get('citation_normalized_percentile', {}) or {}
            percentile_value = citation_normalized_percentile.get('value')
            is_top_1_percent = citation_normalized_percentile.get('is_in_top_1_percent', False)
            cited_by_percentile_year = data.get('cited_by_percentile_year', {}) or {}
            percentile_min = cited_by_percentile_year.get('min')
            percentile_max = cited_by_percentile_year.get('max')
            fwci = data.get('fwci')

            result = {
                'status': 'success',
                'doi': doi_clean,
                'openalex_id': data.get('id'),
                'metadata': {
                    'title': title,
                    'authors': authors,
                    'venue': venue_name,
                    'publication_year': publication_year,
                    'publication_date': publication_date,
                    'type': type_crossref
                },
                'impact_indicators': {
                    'cited_by_count': cited_by_count,
                    'citation_normalized_percentile': {
                        'value': percentile_value,
                        'is_in_top_1_percent': is_top_1_percent
                    },
                    'cited_by_percentile_year': {
                        'min': percentile_min,
                        'max': percentile_max
                    },
                    'fwci': fwci
                },
                'links': {
                    'doi_url': f'https://doi.org/{doi_clean}',
                    'openalex_url': data.get('id')
                }
            }

            return json.dumps(result, ensure_ascii=False, indent=2)

        except requests.exceptions.HTTPError as e:
            error_result = {
                'status': 'error',
                'error_type': 'http_error',
                'error_code': e.response.status_code,
                'message': f'Publication not found for DOI: {doi_clean}' if e.response.status_code == 404 else str(e),
                'doi': doi_clean
            }
            return json.dumps(error_result, ensure_ascii=False, indent=2)

        except requests.exceptions.RequestException as e:
            error_result = {
                'status': 'error',
                'error_type': 'connection_error',
                'message': f'Error connecting to OpenAlex API: {str(e)}',
                'doi': doi_clean
            }
            return json.dumps(error_result, ensure_ascii=False, indent=2)

        except Exception as e:
            error_result = {
                'status': 'error',
                'error_type': 'unexpected_error',
                'message': f'Unexpected error: {str(e)}',
                'doi': doi_clean
            }
            return json.dumps(error_result, ensure_ascii=False, indent=2)
