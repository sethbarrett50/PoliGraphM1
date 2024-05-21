import os
from py2neo import Graph

# Connect to Neo4j
uri = "bolt://localhost:7687"  # Adjust as necessary
user = "neo4j"
password = "your_password"  # Replace with your Neo4j password
graph = Graph(uri, auth=(user, password))

def import_graphml(graphml_path):
    # Build the Cypher command to import the .graphml file
    cypher_command = f"CALL apoc.import.graphml('{graphml_path}', {{batchSize: 10000, storeNodeIds: true}})"
    graph.run(cypher_command)
    print(f"Imported: {graphml_path}")

# Specify the directories containing the .graphml files
directories = [
    "output/GooglePlay_Privacy_Policies",
    "output/IndividWebsite_Privacy_Policies"
]

# Loop through each directory and subdirectory
for directory in directories:
    for subdir, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".graphml"):
                file_path = os.path.join(subdir, file)
                import_graphml(file_path)
