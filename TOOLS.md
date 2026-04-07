## Available Tools

### Installable Package
- **[src/agents4gov_apps/registry.py](src/agents4gov_apps/registry.py)** - Registry for discovering packaged tools after `pip install -e .`

### OpenAlex
- **[src/agents4gov_apps/openalex/open_alex_doi.py](src/agents4gov_apps/openalex/open_alex_doi.py)** - Retrieves metadata and impact indicators for scientific publications using DOI

### OpenML
- **[src/agents4gov_apps/openml/openml_search.py](src/agents4gov_apps/openml/openml_search.py)** - Search for machine learning datasets using semantic similarity with embeddings
- **[src/agents4gov_apps/openml/openml_download.py](src/agents4gov_apps/openml/openml_download.py)** - Download datasets from OpenML by ID and save as CSV
- **[src/agents4gov_apps/openml/openml_knn_train.py](src/agents4gov_apps/openml/openml_knn_train.py)** - Train KNN models with hyperparameter tuning via cross-validation

### CNPq / Lattes
- **[src/agents4gov_apps/cnpq_lattes_navigator_coi_tools/lattes_collector.py](src/agents4gov_apps/cnpq_lattes_navigator_coi_tools/lattes_collector.py)** - Collect Lattes profile data through browser-based navigation
- **[src/agents4gov_apps/cnpq_lattes_navigator_coi_tools/lattes_coi_judge.py](src/agents4gov_apps/cnpq_lattes_navigator_coi_tools/lattes_coi_judge.py)** - Analyze conflicts of interest between a student and committee members

## How to Use Tools in Open WebUI

### Method 1: Import via UI

1. Start Open WebUI server: `open-webui serve`
2. Access the web interface at [http://localhost:8080](http://localhost:8080)
3. Navigate to **Workspace → Tools**
4. Click **Import Tool** or **+ Create Tool**
5. Copy and paste the content of the tool file
6. Save and enable the tool
7. The tool will now be available for agents to use in conversations

### Method 2: Direct File Import

If Open WebUI supports file-based tool loading:

1. Ensure the `tools/` directory is in the Open WebUI tools path
2. Restart Open WebUI to detect new tools
3. Enable the tool in the Tools settings

## Tool Requirements

All tools in this directory require:
- **Python 3.11+**
- **Open WebUI** installed and running
- **pydantic** library for parameter validation

## Creating Your Own Tools

Want to create a new tool? Follow our comprehensive guide:

📖 **[Tool Protocol](docs/tool_protocol.md)**

The tutorial covers:
- Tool structure and class setup
- Parameter validation with Pydantic
- API integration and error handling
- Returning structured JSON data
- Best practices and examples

## Troubleshooting

### Tool Not Appearing in Open WebUI

- Verify the `Tools` class name is correct
- Check for Python syntax errors
- Ensure all required dependencies are installed
- Restart Open WebUI after adding new tools

### Tool Execution Errors

- Check environment variables are set correctly
- Verify internet connectivity for API-based tools
- Review error messages in the JSON response
- Check Open WebUI logs for detailed error information

### Import Errors

- Ensure `pydantic` and other dependencies are installed
- Use Python 3.11+ for compatibility
- Check that the tool file is valid Python code

## Contributing New Tools

When adding a new tool to this directory:

1. **Create the tool file** following the structure in existing tools
2. **Test thoroughly** with various inputs and edge cases
3. **Document the tool** with a README.md in its subdirectory
4. **Add it to this README** under "Available Tools"
5. **Follow best practices** outlined in the [protocol](docs/tool_protocol.md)

## Additional Resources

- **[Tool Protocol](docs/tool_protocol.md)** - Step-by-step guide for creating tools as packaged modules
- **[Open WebUI Tools Guide](https://docs.openwebui.com/features/plugin/tools)** - Official Open WebUI tools documentation
- **[Project Documentation](../docs/README.md)** - Main documentation hub
