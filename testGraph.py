import os
import networkx as nx
import matplotlib.pyplot as plt

from py2neo import Graph, Node, Relationship



# Your database connection details
url = "bolt://localhost:7687"
username = "neo4j"
password = "password"
database = "neo4j"

# Connect to your Neo4j database
neo4j_graph = Graph(url, name=database, auth=(username, password))

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