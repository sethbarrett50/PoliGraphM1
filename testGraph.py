import os
import networkx as nx
from py2neo import Graph, Node, Relationship
import matplotlib.pyplot as plt

# Set up Neo4j connection
neo4j_graph = Graph("bolt://localhost:7687", auth=("neo4j", "password"))

# Function to ingest .graphml files into Neo4j
def ingest_graphml_files(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".graphml"):
                file_path = os.path.join(root, file)
                print(f"Ingesting {file_path}...")
                g = nx.read_graphml(file_path)
                for node in g.nodes():
                    n = Node(node)
                    neo4j_graph.create(n)

                for edge in g.edges():
                    source_node = neo4j_graph.nodes.match("name", edge[0]).first()
                    target_node = neo4j_graph.nodes.match("name", edge[1]).first()
                    rel = Relationship(source_node, edge[2], target_node)
                    neo4j_graph.create(rel)

# Ingest .graphml files from both directories
ingest_graphml_files("./output/GooglePlay/")
ingest_graphml_files("./output/IndividualWebsite/")

# Query Neo4j to find common relationships
query = """
    MATCH (n1:Node)-[:RELATIONSHIP_TYPE]->(m1:Node)
    MATCH (n2:Node)-[:RELATIONSHIP_TYPE]->(m2:Node)
    WHERE n1.name IN ['Graph1_Node1', 'Graph1_Node2'] AND n2.name IN ['Graph2_Node1', 'Graph2_Node2']
    RETURN n1, m1, n2, m2
"""
results = neo4j_graph.run(query).data()

# Create a new graph to visualize common relationships
common_graph = nx.DiGraph()

# Add nodes and edges to the common graph
for result in results:
    n1 = result['n1']['name']
    m1 = result['m1']['name']
    n2 = result['n2']['name']
    m2 = result['m2']['name']
    common_graph.add_edge(n1, m1)
    common_graph.add_edge(n2, m2)

# Visualize the common graph
pos = nx.spring_layout(common_graph)
nx.draw_networkx(common_graph, pos, with_labels=True, node_color='lightblue')
plt.show()