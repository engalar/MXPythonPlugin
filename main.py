import os
import re
import json
from collections import defaultdict
import pandas as pd
from pprint import pprint

# --- PART 1: Parser for the userlib Directory ---

def parse_userlib_dir(directory_path: str) -> list:
    """
    Analyzes a Mendix userlib directory to parse JARs and identify their sources.

    Args:
        directory_path (str): The path to the userlib folder.

    Returns:
        list: A list of dictionaries, each representing a dependency.
    """
    print(f"Analyzing userlib directory: {directory_path}...")
    
    # Regex to extract library name and version from a JAR filename
    jar_pattern = re.compile(r'^(.*?)-(\d+(?:\.\d+)*.*?)\.jar$')
    generic_jar_pattern = re.compile(r'^(.*?)_([\d\.]+.*?)\.jar$')

    # Regex to parse the '.RequiredLib' marker files
    required_by_pattern = re.compile(r'^(.*\.jar)\.(.*?)\.(RequiredLib|Required\.by.*)$')

    jar_info = {}

    try:
        filenames = os.listdir(directory_path)
    except FileNotFoundError:
        print(f"Error: Directory not found at '{directory_path}'")
        return []

    # First pass: Parse all JAR files
    for filename in filenames:
        if filename.endswith('.jar'):
            lib_name, version = None, None
            match = jar_pattern.match(filename)
            if not match:
                match = generic_jar_pattern.match(filename)

            if match:
                lib_name, version = match.groups()
                # Normalize common library names for better grouping
                lib_name = lib_name.replace('org.apache.commons.', 'commons-')
                lib_name = lib_name.replace('org.apache.httpcomponents.', '')
            
            jar_info[filename] = {
                'library_name': lib_name if lib_name else filename.replace('.jar', ''),
                'version': version if version else 'unknown',
                'source': 'userlib',
                'details': {'filename': filename, 'required_by': set()}
            }

    # Second pass: Parse '.RequiredLib' files to add context
    for filename in filenames:
        if 'Required' in filename:
            match = required_by_pattern.match(filename)
            if match:
                jar_filename, module_name, _ = match.groups()
                if jar_filename in jar_info:
                    jar_info[jar_filename]['details']['required_by'].add(module_name)
    
    # Convert the processed data into the final list format
    dependency_list = []
    for info in jar_info.values():
        required_by_str = ", ".join(sorted(list(info['details']['required_by']))) or "Unknown"
        info['details'] = f"File: {info['details']['filename']} (Required by: {required_by_str})"
        dependency_list.append(info)
        
    print(f"Found {len(dependency_list)} JARs in userlib.")
    return dependency_list


# --- PART 2: Parser for the SBOM JSON file ---

def parse_sbom_file(sbom_path: str) -> list:
    """
    Parses a CycloneDX SBOM JSON file to extract dependency information.

    Args:
        sbom_path (str): The path to the sbom.json file.

    Returns:
        list: A list of dictionaries, each representing a dependency.
    """
    print(f"Analyzing SBOM file: {sbom_path}...")
    dependency_list = []
    
    try:
        with open(sbom_path, 'r', encoding='utf-8') as f:
            sbom_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: SBOM file not found at '{sbom_path}'")
        return []
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{sbom_path}'")
        return []

    components = sbom_data.get('components', [])
    for comp in components:
        # We use the component 'name' as the library_name for consistency
        lib_name = comp.get('name')
        if lib_name:
            dependency_list.append({
                'library_name': lib_name,
                'version': comp.get('version', 'unknown'),
                'source': 'SBOM (vendorlib)',
                'details': f"PURL: {comp.get('purl', 'N/A')}"
            })
            
    print(f"Found {len(dependency_list)} components in SBOM.")
    return dependency_list


# --- PART 3: Main Analysis Logic ---

def analyze_conflicts(dependencies: list) -> dict:
    """
    Analyzes a combined list of dependencies to find version conflicts.

    Args:
        dependencies (list): The merged list of dependencies from all sources.

    Returns:
        dict: A dictionary where keys are conflicting library names and values
              are lists of their different versions and sources.
    """
    grouped_libs = defaultdict(list)
    for dep in dependencies:
        # Ignore dependencies with unknown versions for conflict analysis
        if dep['version'] != 'unknown':
            grouped_libs[dep['library_name']].append({
                'version': dep['version'],
                'source': dep['source'],
                'details': dep['details']
            })

    conflicts = {}
    for lib_name, versions_info in grouped_libs.items():
        unique_versions = {info['version'] for info in versions_info}
        if len(unique_versions) > 1:
            conflicts[lib_name] = versions_info
            
    return conflicts


# --- SCRIPT EXECUTION ---
if __name__ == "__main__":
    # --- CONFIGURATION: Please update these paths for your project ---
    # Path to your Mendix project's userlib directory
    USERLIB_PATH = 'D:/Users/Wengao.Liu/Mendix/App/userlib'
    # Path to your generated SBOM file (e.g., from vendorlib)
    SBOM_PATH = 'D:/Users/Wengao.Liu/Mendix/App/vendorlib/vendorlib-sbom.json'

    # 1. Parse dependencies from both sources
    userlib_deps = parse_userlib_dir(USERLIB_PATH)
    sbom_deps = parse_sbom_file(SBOM_PATH)

    # 2. Combine the lists
    all_dependencies = userlib_deps + sbom_deps

    if not all_dependencies:
        print("\nNo dependencies found to analyze. Please check your paths.")
    else:
        # 3. Create a comprehensive DataFrame for reporting
        df = pd.DataFrame(all_dependencies)
        # Reorder columns for better readability
        df = df[['library_name', 'version', 'source', 'details']]
        df = df.sort_values(by=['library_name', 'version']).reset_index(drop=True)

        # 4. Analyze for conflicts
        conflict_report = analyze_conflicts(all_dependencies)

        # 5. Print the results
        print("\n\n" + "="*80)
        print("      Mendix Project JAR Dependency and Conflict Analysis Report")
        print("="*80)
        
        print("\n--- Full List of Detected Dependencies ---")
        pd.set_option('display.max_rows', None)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 120)
        print(df.to_string())

        print("\n\n" + "="*80)
        if conflict_report:
            print("--- !!! POTENTIAL CONFLICTS DETECTED !!! ---")
            print("The following libraries were found with multiple different versions.\n")
            pprint(conflict_report)
            print("\n[Action Required] JAR version conflicts ('JAR Hell') can cause serious runtime errors.")
            print("Review the conflicts above and try to align the versions by updating modules or managing dependencies manually.")
        else:
            print("--- No direct version conflicts were detected. ---")
            print("All libraries with identifiable versions appear to have only one version.")
        
        print("="*80)




# ❯ & D:/Python311/python.exe d:/Users/Wengao.Liu/.mxplugins/main.py
# Analyzing userlib directory: D:/Users/Wengao.Liu/Mendix/App/userlib...
# Found 25 JARs in userlib.
# Analyzing SBOM file: D:/Users/Wengao.Liu/Mendix/App/vendorlib/vendorlib-sbom.json...
# Found 1 components in SBOM.


# ================================================================================
#       Mendix Project JAR Dependency and Conflict Analysis Report
# ================================================================================

# --- Full List of Detected Dependencies ---
#                 library_name   version            source                                                                                           details
# 0                 activation     1.1.1           userlib                                               File: activation-1.1.1.jar (Required by: MendixSSO)
# 1              commons-codec      1.15           userlib                                     File: commons-codec-1.15.jar (Required by: SAPODataConnector)
# 2                 commons-io     2.3.0           userlib                                  File: org.apache.commons.io-2.3.0.jar (Required by: UnitTesting)
# 3                 commons-io       2.6  SBOM (vendorlib)                                                PURL: pkg:maven/commons-io/commons-io@2.6?type=jar
# 4               commons-lang       2.5           userlib                                                 File: commons-lang-2.5.jar (Required by: Unknown)
# 5              commons-lang3       3.9           userlib                                      File: commons-lang3-3.9.jar (Required by: ODataQueryBuilder)
# 6            commons-logging       1.2           userlib                                    File: commons-logging-1.2.jar (Required by: SAPODataConnector)
# 7                  fluent-hc     4.5.3           userlib                                        File: fluent-hc-4.5.3.jar (Required by: SAPODataConnector)
# 8                      guice       2.0           userlib                                                        File: guice-2.0.jar (Required by: Unknown)
# 9                 httpclient     4.4.1           userlib                   File: org.apache.httpcomponents.httpclient_4.4.1.jar (Required by: UnitTesting)
# 10                httpclient    4.5.13           userlib                                      File: httpclient-4.5.13.jar (Required by: SAPODataConnector)
# 11                  httpcore     4.4.1           userlib                         File: org.apache.httpcomponents.httpcore_4.4.1.jar (Required by: Unknown)
# 12                  httpcore     4.4.6           userlib                                         File: httpcore-4.4.6.jar (Required by: SAPODataConnector)
# 13       jackson-annotations    2.13.4           userlib                                       File: jackson-annotations-2.13.4.jar (Required by: Unknown)
# 14              jackson-core    2.13.4           userlib                                              File: jackson-core-2.13.4.jar (Required by: Unknown)
# 15          jackson-databind  2.13.4.2           userlib                                        File: jackson-databind-2.13.4.2.jar (Required by: Unknown)
# 16                  java-jwt    3.19.1           userlib                                                  File: java-jwt-3.19.1.jar (Required by: Unknown)
# 17                javax.json       1.1           userlib                                         File: javax.json-1.1.jar (Required by: SAPODataConnector)
# 18            javax.json-api       1.0           userlib                                     File: javax.json-api-1.0.jar (Required by: SAPODataConnector)
# 19                javax.mail     1.6.2           userlib                                               File: javax.mail-1.6.2.jar (Required by: MendixSSO)
# 20                     junit      4.11           userlib                                                   File: junit-4.11.jar (Required by: UnitTesting)
# 21             kotlin-stdlib     1.9.0           userlib                                    File: kotlin-stdlib-1.9.0.jar (Required by: SAPODataConnector)
# 22                    okhttp    4.10.0           userlib                                          File: okhttp-4.10.0.jar (Required by: SAPODataConnector)
# 23                      okio     3.5.0           userlib                                             File: okio-3.5.0.jar (Required by: SAPODataConnector)
# 24                  okio-jvm     3.5.0           userlib                                         File: okio-jvm-3.5.0.jar (Required by: SAPODataConnector)
# 25  org.apache.commons.lang3   unknown           userlib  File: org.apache.commons.lang3.jar (Required by: ObjectHandling, SAPODataConnector, UnitTesting)


# ================================================================================
# --- !!! POTENTIAL CONFLICTS DETECTED !!! ---
# The following libraries were found with multiple different versions.

# {'commons-io': [{'details': 'File: org.apache.commons.io-2.3.0.jar (Required '
#                             'by: UnitTesting)',
#                  'source': 'userlib',
#                  'version': '2.3.0'},
#                 {'details': 'PURL: '
#                             'pkg:maven/commons-io/commons-io@2.6?type=jar',
#                  'source': 'SBOM (vendorlib)',
#                  'version': '2.6'}],
#  'httpclient': [{'details': 'File: httpclient-4.5.13.jar (Required by: '
#                             'SAPODataConnector)',
#                  'source': 'userlib',
#                  'version': '4.5.13'},
#                 {'details': 'File: '
#                             'org.apache.httpcomponents.httpclient_4.4.1.jar '
#                             '(Required by: UnitTesting)',
#                  'source': 'userlib',
#                  'version': '4.4.1'}],
#  'httpcore': [{'details': 'File: httpcore-4.4.6.jar (Required by: '
#                           'SAPODataConnector)',
#                'source': 'userlib',
#                'version': '4.4.6'},
#               {'details': 'File: org.apache.httpcomponents.httpcore_4.4.1.jar '
#                           '(Required by: Unknown)',
#                'source': 'userlib',
#                'version': '4.4.1'}]}

# [Action Required] JAR version conflicts ('JAR Hell') can cause serious runtime errors.
# Review the conflicts above and try to align the versions by updating modules or managing dependencies manually.
# ================================================================================