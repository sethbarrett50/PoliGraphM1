import os
import networkx as nx

from py2neo import Graph, Node, Relationship

url = "bolt://localhost:7687"
username = "neo4j"
password = "password"
database = "neo4j"

# Connect to your Neo4j database
neo4j_graph = Graph(url, name=database, auth=(username, password))

def ingest_graphml_files(directory):
    # Start processing from the root directory
    print(f"Starting ingestion from directory: {directory}")
    
    # Walk through the directory structure
    for root, dirs, files in os.walk(directory):
        print(f"Visiting directory: {root}")  # Debug output to track which directory is being processed
        
        for file in files:
            if file.endswith(".graphml"):
                file_path = os.path.join(root, file)
                print(f"Ingesting {file_path}...")  # Confirm which file is being ingested
                
                try:
                    g = nx.read_graphml(file_path)  # Read the GraphML file
                    
                    # Begin a transaction for batch processing
                    tx = neo4j_graph.begin()
                    node_map = {}
                    
                    # Create nodes
                    for node_id, node_attrs in g.nodes(data=True):
                        n = Node("Node", **node_attrs)
                        tx.create(n)
                        node_map[node_id] = n
                    
                    # Create relationships
                    for source, target, edge_attrs in g.edges(data=True):
                        rel_type = edge_attrs.get('type', 'RELATED_TO')  # Default to 'RELATED_TO' if no type specified
                        rel = Relationship(node_map[source], rel_type, node_map[target], **edge_attrs)
                        tx.create(rel)
                    
                    tx.commit()  # Commit transaction
                except Exception as e:
                    print(f"Failed to ingest {file_path}: {str(e)}")  # Print error if ingestion fails


# Ingest .graphml files from both directories
ingest_graphml_files("./output/GooglePlay_Privacy_Policies/")
ingest_graphml_files("./output/IndividWebsite_Privacy_Policies/")
