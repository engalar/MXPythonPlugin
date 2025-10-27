# Mendix Log Extractor Plugin

## Business Requirements

### Overview
A comprehensive Mendix Studio Pro plugin that extracts diagnostic information, logs, and project metadata to assist developers in troubleshooting, debugging, and forum support requests.

### Core Requirements

#### 1. Log Extraction
- **Studio Pro Logs**: Extract logs from Windows AppData directory (`%LOCALAPPDATA%\Mendix\log\{version}\log.txt`)
- **Git Logs**: Extract Git operation logs from (`%LOCALAPPDATA%\Mendix\log\{version}\git\git.log.txt`)
- **Dynamic Version Detection**: Automatically detect current Mendix version from the active project
- **Log File Reading**: Read last 1000 lines of log files with proper error handling

#### 2. Project Analysis
- **Module Information**: Extract all modules with their entities, microflows, and pages
- **JAR Dependencies**: Scan `userlib` directory for Java dependencies
- **Frontend Components**: Identify widgets and custom components in `widgets` and `javascriptsource` directories
- **File Metadata**: Include file sizes, modification dates, and paths

#### 3. Forum Integration
- **Automated Formatting**: Convert extracted data into forum-friendly markdown format
- **Copy-to-Clipboard**: One-click copy functionality for forum posts
- **Structured Output**: Organized sections for version, modules, dependencies, and logs

#### 4. User Experience
- **Tabbed Interface**: Organized sections for different data types
- **Progress Indicators**: Real-time feedback for long-running operations
- **Error Handling**: Graceful handling of missing files and permissions
- **Responsive Design**: Clean, modern UI using React and Tailwind CSS

### Target Users
- Mendix developers seeking technical support
- Forum moderators assisting with troubleshooting
- Developers debugging application issues
- Team leads analyzing project structure

## Technical Specification

### Architecture
The plugin follows a clean architecture pattern with separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (React)                        │
├─────────────────────────────────────────────────────────────┤
│  UI Components  │  State Management  │  Communication     │
│  - Tab Panels   │  - React Hooks     │  - Message Passing │
│  - Progress UI  │  - RxJS Streams    │  - Error Handling  │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                  Backend (Python)                          │
├─────────────────────────────────────────────────────────────┤
│  RPC Handlers   │  Job Handlers     │  Business Logic     │
│  - GetVersion   │  - ExtractAll     │  - LogExtractor     │
│  - GetLogs      │  - FormatForum    │  - File Operations  │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                  Data Sources                              │
├─────────────────────────────────────────────────────────────┤
│  File System    │  Mendix API    │  Project Structure     │
│  - AppData      │  - Modules     │  - Directory Scanning  │
│  - Userlib      │  - Version     │  - Metadata Extraction │
└─────────────────────────────────────────────────────────────┘
```

### Technology Stack

#### Frontend
- **React 18**: Modern functional components with hooks
- **Tailwind CSS**: Utility-first CSS framework
- **RxJS**: Reactive programming for real-time updates
- **React Spring**: Smooth animations and transitions
- **REDI**: Dependency injection for React

#### Backend
- **Python 3.x**: Core business logic
- **pythonnet**: .NET integration with Mendix APIs
- **dependency-injector**: IoC container for dependency management
- **System.Text.Json**: .NET JSON serialization

#### Communication
- **Message Passing**: JSON-RPC style communication
- **Progress Updates**: Real-time job progress streaming
- **Error Handling**: Comprehensive error capture and display

### Key Components

#### Backend Components

**LogExtractor Class**
- `get_mendix_log_path(version)`: Constructs log file paths
- `read_log_file(file_path, max_lines)`: Safely reads log files
- `extract_studio_pro_logs(version)`: Extracts Studio Pro logs
- `extract_git_logs(version)`: Extracts Git logs
- `extract_modules_info()`: Analyzes project modules
- `extract_jar_dependencies()`: Scans for JAR files
- `extract_frontend_components()`: Identifies frontend components
- `format_for_forum(data)`: Creates forum-ready markdown

**RPC Handlers**
- `GetVersionRpc`: Retrieves Mendix version and project info
- `GetStudioProLogsRpc`: Fetches Studio Pro logs
- `GetGitLogsRpc`: Fetches Git logs
- `GetModulesInfoRpc`: Gets module information
- `GetJarDependenciesRpc`: Gets JAR dependencies
- `GetFrontendComponentsRpc`: Gets frontend components
- `FormatForForumRpc`: Formats data for forum posting

**Job Handlers**
- `ExtractAllLogsJob`: Background extraction of all log types

#### Frontend Components

**Main App Component**
- Tab navigation system
- Progress tracking
- Error display
- Data state management

**Panel Components**
- Overview dashboard
- Log viewers with syntax highlighting
- Module browser
- Dependency explorer
- Forum export preview

### File Structure
```
log-extractor/
├── main.py              # Backend logic and handlers
├── index.html           # Frontend React application
├── manifest.json        # Plugin manifest with metadata and configuration
├── README.md           # Documentation
```

### API Specification

#### RPC Methods

**`logs:getVersion`**
- Returns: `{ version: string, projectPath: string }`
- Description: Gets current Mendix version and project path

**`logs:getStudioProLogs`**
- Params: `{ version: string }`
- Returns: `{ version: string, logPath: string, exists: boolean, lines: string[], lastModified: string }`
- Description: Extracts Studio Pro logs for specified version

**`logs:getGitLogs`**
- Params: `{ version: string }`
- Returns: `{ version: string, logPath: string, exists: boolean, lines: string[], lastModified: string }`
- Description: Extracts Git logs for specified version

**`logs:getModulesInfo`**
- Returns: `[{ id: string, name: string, type: string, entities: [], microflows: [], pages: [] }]`
- Description: Gets comprehensive module information

**`logs:getJarDependencies`**
- Returns: `[{ name: string, path: string, size: number, lastModified: string }]`
- Description: Lists all JAR dependencies

**`logs:getFrontendComponents`**
- Returns: `[{ name: string, path: string, size: number, lastModified: string, type: string }]`
- Description: Lists frontend components and widgets

**`logs:formatForForum`**
- Params: `{ data: object }`
- Returns: `{ formattedText: string, timestamp: string }`
- Description: Formats extracted data for forum posting

#### Job Methods

**`logs:extractAll`**
- Params: `{ version: string }`
- Returns: `{ data: object, forumFormatted: string }`
- Description: Extracts all log types and formats for forum

### Error Handling

#### Backend Error Handling
- File system errors (missing files, permissions)
- Mendix API errors (version detection, module access)
- JSON serialization errors
- Comprehensive traceback capture

#### Frontend Error Handling
- Network timeouts (10-second RPC timeout)
- Backend error display with expandable tracebacks
- Graceful degradation for missing data
- User-friendly error messages

### Security Considerations

#### File System Access
- Read-only operations (no file modifications)
- Path validation to prevent directory traversal
- Encoding handling for text files (UTF-8 with fallback)

#### Data Privacy
- No sensitive data transmission
- Local file system access only
- No external network requests

### Performance Optimization

#### Backend
- Efficient file reading (last 1000 lines only)
- Cached Mendix API calls
- Background job processing
- Memory-efficient streaming

#### Frontend
- Lazy loading of tab content
- Debounced UI updates
- Efficient React re-renders
- Optimized bundle size

### Testing Strategy

#### Unit Tests
- Individual component testing
- API method validation
- Error scenario coverage

#### Integration Tests
- End-to-end workflow testing
- Cross-component communication
- Real-time update verification

### Deployment

#### Installation
1. Copy plugin files to Mendix plugins directory
2. Ensure Python dependencies are available
3. Restart Mendix Studio Pro

#### Configuration
- No manual configuration required
- Automatic version detection
- Adaptive to different project structures

### Future Enhancements

#### Planned Features
- Log filtering and search functionality
- Export to multiple formats (JSON, XML, CSV)
- Custom log path configuration
- Integration with external logging services
- Log analysis and pattern detection
- Performance metrics extraction
- Team collaboration features

#### Technical Improvements
- Caching mechanism for frequently accessed data
- Incremental updates for large projects
- Plugin configuration persistence
- Multi-language support

## Usage Instructions

### Basic Usage
1. Open Mendix Studio Pro with your project
2. Navigate to the Log Extractor plugin
3. Click "Extract All Logs" to gather comprehensive information
4. Use individual tabs to view specific data types
5. Click "Format for Forum" to generate forum-ready content
6. Use "Copy to Clipboard" to copy formatted content

### Advanced Usage
- Extract individual log types for targeted analysis
- Monitor real-time progress during extraction
- Review error details with full tracebacks
- Export data for external analysis tools

### Troubleshooting
- Check file permissions for log directory access
- Verify Mendix version compatibility
- Review error messages for specific issues
- Ensure Python dependencies are properly installed
- Check `manifest.json` for correct plugin metadata and configuration

This plugin provides a comprehensive solution for Mendix developers to extract, analyze, and share diagnostic information efficiently and effectively.