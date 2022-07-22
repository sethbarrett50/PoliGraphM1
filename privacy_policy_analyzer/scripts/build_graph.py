#!/usr/bin/env python3

import argparse
import itertools
import json
import os
import re
from collections import defaultdict, deque

import networkx as nx
import spacy
import yaml
from privacy_policy_analyzer.document import PolicyDocument
from privacy_policy_analyzer.named_entity_recognition import ACTOR_KEYWORDS, DATATYPE_KEYWORDS
from privacy_policy_analyzer.phrase_normalization import EntityMatcher, RuleBasedPhraseNormalizer
from privacy_policy_analyzer.purpose_classification import PurposeClassifier


def expand_phrase(root_token):
    doc = root_token.doc

    def has_alpha(s):
        return re.search(r"[a-zA-Z]", s, flags=re.ASCII) is not None

    def should_include(current_token, in_left_modifier=False):
        if current_token._.src is None:
            return False

        match current_token.dep_:
            case "dep" | "meta":
                # NLP glitches
                return current_token.ent_type_ != ""
            case "punct":
                # Keep punct only it's inside a word/entity (e.g. health-related info)
                flag = (current_token.i > 0 and current_token.i + 1 < len(doc)
                        and doc[current_token.i - 1].whitespace_ == "" and has_alpha(doc[current_token.i - 1].text)
                        and current_token.whitespace_ == "" and has_alpha(doc[current_token.i + 1].text))
                flag |= current_token.ent_type_ != ""
                flag |= in_left_modifier

                if not flag:
                    return False

        if current_token.dep_ in ["amod", "nmod", "nummod", "compound"] and current_token.i < current_token.head.i:
            in_left_modifier = True

        for c in current_token.children:
            if not should_include(c, in_left_modifier):
                return False

        return True

    # Noun phrase, try to include simple children
    bfs_queue = [root_token]

    while len(bfs_queue) > 0:
        token = bfs_queue.pop(0)

        left_idx = token.i
        for child in sorted(token.lefts, reverse=True):
            if should_include(child):
                child_indices = sorted(t.i for t in child.subtree)

                if (child_indices[-1] - child_indices[0] == len(child_indices) - 1
                    and left_idx - 1 == child_indices[-1]):
                    left_idx = child_indices[0]
                else:
                    break
            else:
                break

        right_idx = token.i + 1
        for child in sorted(token.rights):
            if child.dep_ in ["conj", "appos"]:
                bfs_queue.append(child)
                break
            elif should_include(child):
                child_indices = sorted(t.i for t in child.subtree)

                if (child_indices[-1] - child_indices[0] == len(child_indices) - 1
                    and right_idx == child_indices[0]):
                    right_idx = child_indices[-1] + 1
                else:
                    break
            else:
                break

        # strip suffix "cc" words (e.g. and/or)
        if doc[right_idx - 1].dep_ == "cc":
            right_idx -= 1

        # strip surrounding puncts
        while doc[left_idx].lemma_ in '"\'([':
            left_idx += 1

        while doc[right_idx - 1].lemma_ in '"\')]':
            right_idx -= 1

        yield doc[left_idx:right_idx]


def simplify_phrase(phrase):
    trivial_words = frozenset([
        "some", "all", "any", "type", "variety", "category", "example",
        "more", "such", "other", "following", "additional",
        "certain", "similar", "limited", "various", "detailed",
        "further", "enough", "e.g.", "i.e.",
        "which", "that",
    ])

    def dfs(token, state):
        if token.lemma_ in trivial_words:
            return

        match state:
            case "compound" | "nmod" | "pobj" | "nsubj" | "dobj":
                next_states = {"compound", "amod", "nmod", "prep", "relcl", "acl"}
            case "prep":
                next_states = {"pobj"}
            case "amod":
                next_states = {"advmod", "npadvmod"}
            case "relcl" | "acl":
                next_states = {"nsubj", "dobj"}
            case _:
                yield token
                return

        for t in token.children:
            if t in phrase and t.dep_ in next_states:
                yield from dfs(t, t.dep_)

        yield token

    return sorted(dfs(phrase.root, "compound"))


def dag_add_edge(G, n1, n2, *args, **kwargs):
    if n1 == n2 or n2 in nx.ancestors(G, n1):
        return False
    else:
        G.add_edge(n1, n2, *args, **kwargs)
        return True


class GraphBuilder:
    def __init__(self, phrase_map, entity_map):
        with open(phrase_map, "r", encoding="utf-8") as fin:
            phrase_map_rules = yaml.safe_load(fin)

        self.entity_mapper = EntityMatcher(entity_map)
        self.data_phrase_normalizer = RuleBasedPhraseNormalizer(phrase_map_rules["DATA"])
        self.actor_phrase_normalizer = RuleBasedPhraseNormalizer(phrase_map_rules["ACTOR"])
        self.purpose_classifier = PurposeClassifier()

    def build_graph(self, document: PolicyDocument):
        stage1_graph = self.__build_graph_stage1(document)
        stage2_graph = self.__build_graph_stage2(document, stage1_graph)
        return stage2_graph

    def __build_graph_stage1(self, document: PolicyDocument):
        stage1_graph = nx.DiGraph()

        # Step 1: Infer phrase type using NER label
        for src in document.token_relationship.nodes:
            token = document.get_token_with_src(src)

            match token._.ent_type:
                case "NN":
                    # unknown type, figure it out later
                    continue
                case "DATA":
                    stage1_graph.add_node(src, token=token, type="DATA")
                case "ACTOR":
                    stage1_graph.add_node(src, token=token, type="ACTOR")
                case "OTHER":
                    # Will eventually remove these nodes
                    stage1_graph.add_node(src, token=token, type="OTHER")

        # Step 2: Infer phrase type using COLLECT / NOT_COLLECT relationship
        for src1, src2, data in document.token_relationship.edges(data=True):
            relationship = data["relationship"]

            if relationship in ["COLLECT", "NOT_COLLECT"]:
                token1 = document.get_token_with_src(src1)
                token2 = document.get_token_with_src(src2)

                if src1 not in stage1_graph:
                    stage1_graph.add_node(src1, token=token1, type="ACTOR")

                if src2 not in stage1_graph:
                    stage1_graph.add_node(src2, token=token2, type="DATA")

                if [stage1_graph.nodes[s]["type"] for s in (src1, src2)] == ["ACTOR", "DATA"]:
                    # This will never create a circle
                    stage1_graph.add_edge(src1, src2, relationship=relationship)

        # Step 2.5: Annotate purposes
        data_type_to_purpose_text_list = defaultdict(list)
        all_purpose_text = set()

        for data_type, node_data in stage1_graph.nodes(data=True):
            if node_data["type"] != "DATA":
                continue

            for _, purpose_src, edge_data in document.token_relationship.edges(data_type, data=True):
                if edge_data["relationship"] == "PURPOSE":
                    purpose_root = document.get_token_with_src(purpose_src)
                    right_end = max(t.i for t in purpose_root.subtree) + 1
                    purpose_part = purpose_root.doc[purpose_root.i:right_end]

                    data_type_to_purpose_text_list[data_type].append(purpose_part.text)
                    all_purpose_text.add(purpose_part.text)

        all_purpose_text = list(all_purpose_text)
        purpose_text_to_purpose = dict(zip(all_purpose_text, self.purpose_classifier.classify(all_purpose_text)))

        for data_type, purpose_text_list in data_type_to_purpose_text_list.items():
            edge_purposes = list()

            for purpose_text in purpose_text_list:
                edge_purposes.append((purpose_text_to_purpose[purpose_text], purpose_text))

            for _, _, edge_data in stage1_graph.in_edges(data_type, data=True):
                if edge_data["relationship"] == "COLLECT":
                    edge_data["purposes"] = edge_purposes

        # Step 3: Infer phrase type using SUBSUM / COREF relationship
        # Run a BFS starting from nodes with known types.
        bfs_queue = deque(stage1_graph.nodes)
        visited_nodes = set(stage1_graph.nodes)

        while len(bfs_queue) > 0:
            src1 = bfs_queue.popleft()
            phrase_type = stage1_graph.nodes[src1]["type"]

            if phrase_type == "OTHER":
                continue

            in_edge_view = document.token_relationship.in_edges(src1, data=True)
            out_edge_view = document.token_relationship.out_edges(src1, data=True)

            for edge_from, edge_to, data in itertools.chain(in_edge_view, out_edge_view):
                if data["relationship"] in ["SUBSUM", "COREF"]:
                    src2 = edge_to if src1 == edge_from else edge_from

                    if src2 not in stage1_graph:
                        token2 = document.get_token_with_src(src2)
                        stage1_graph.add_node(src2, token=token2, type=phrase_type)

                        if src2 in visited_nodes:
                            # Avoid loop
                            visited_nodes.add(src2)
                            bfs_queue.append(src2)

                    if stage1_graph.nodes[src2]["type"] == phrase_type:
                        # Call dag_add_edge to safely add an edge without creating a circle
                        dag_add_edge(stage1_graph, edge_from, edge_to, relationship=data["relationship"])

        # Step 4: Remove "OTHER" phrases
        to_remove = [n for n, d in stage1_graph.nodes(data=True) if d['type'] == 'OTHER']
        stage1_graph.remove_nodes_from(to_remove)

        # Step 5: Infer meaning of each phrase using normalizers
        # Follow topological order to resolve coreferences
        for src in reversed(list(nx.topological_sort(stage1_graph))):
            data = stage1_graph.nodes[src]

            token = data["token"]
            # Normalized terms
            data["normalized_terms"] = normalized_terms = set()
            # Main phrase of a coreference. Technically we allow a phrase to have more than one COREF edges
            coref_main = set()

            for _, ref_src, edge_data in stage1_graph.out_edges(src, data=True):
                if edge_data["relationship"] == "COREF":
                    # for coreferences, copy normalized_terms from referred phrase
                    coref_main.update(stage1_graph.nodes[ref_src]["coref_main"] or [ref_src])
                    normalized_terms.update(data["normalized_terms"])

            if coref_main:
                data["coref_main"] = coref_main
                continue
            else:
                data["coref_main"] = {src}

            for phrase in expand_phrase(token):
                match data["type"]:
                    case "DATA":
                        normalized_terms = list(self.data_phrase_normalizer.normalize(phrase))

                        if len(normalized_terms) == 0:
                            simplified = " ".join(t.lemma_ for t in simplify_phrase(phrase))

                            if simplified:
                                if simplified in ["data", "datum", "information"]:
                                    normalized_terms.append('UNSPECIFIC_DATA')
                                elif simplified and simplified not in DATATYPE_KEYWORDS:
                                    # if simplified in DATATYPE_KEYWORDS, the term is too "common" to be considered
                                    normalized_terms.append(simplified)
                    case "ACTOR":
                        normalized_terms = list(self.actor_phrase_normalizer.normalize(phrase))

                        if any(t.pos_ == "PROPN" for t in phrase):
                            if entity_name := self.entity_mapper.match_name(phrase.text):
                                normalized_terms.append(entity_name)

                        if len(normalized_terms) == 0:
                            simplified = " ".join(t.lemma_ for t in simplify_phrase(phrase))

                            if simplified and simplified != "you":
                                if simplified in ACTOR_KEYWORDS:
                                    normalized_terms.append('UNSPECIFIC_ENTITY')
                                else:
                                    normalized_terms.append(simplified)
                    case _:
                        raise ValueError("Invalid type")

                # print(phrase, normalized_terms)
                data["normalized_terms"].update(normalized_terms)

        return stage1_graph

    def __build_graph_stage2(self, document: PolicyDocument, stage1_graph: nx.DiGraph):
        stage2_graph = nx.MultiDiGraph()

        for _, node_data in stage1_graph.nodes(data=True):
            stage2_graph.add_nodes_from(node_data["normalized_terms"], type=node_data["type"])

        for src1, src2, edge_data in stage1_graph.edges(data=True):
            relationship = edge_data["relationship"]

            if relationship == "COREF":
                continue

            coref_src1 = stage1_graph.nodes[src1]["coref_main"]
            coref_src2 = stage1_graph.nodes[src2]["coref_main"]

            normalized_terms1 = set.union(*(stage1_graph.nodes[i]["normalized_terms"] for i in coref_src1))
            normalized_terms2 = set.union(*(stage1_graph.nodes[i]["normalized_terms"] for i in coref_src2))

            edge_sources = set.union(coref_src1, coref_src2)
            edge_sentences = []

            for segment_id in sorted(set(s[0] for s in edge_sources)):
                doc = document.get_doc_without_context(document.segments[segment_id])

                for sent in doc.sents:
                    if any(t._.src in edge_sources for t in sent):
                        edge_sentences.append(sent.text)

            for n1, n2 in itertools.product(normalized_terms1, normalized_terms2):
                if not stage2_graph.has_edge(n1, n2, key=relationship):
                    if dag_add_edge(stage2_graph, n1, n2, key=relationship, sources=[], text=[]):
                        if relationship == "COLLECT":
                            stage2_graph[n1][n2][relationship]["purposes"] = []
                    else:
                        continue

                stage2_graph[n1][n2][relationship]["sources"].append(sorted(edge_sources))
                stage2_graph[n1][n2][relationship]["text"].append(" | ".join(edge_sentences))

                if relationship == "COLLECT":
                    stage2_graph[n1][n2][relationship]["purposes"].extend(edge_data.get("purposes", []))

        edges_to_remove = []
        # Some sentences lead to subsumption relationship between 1st/3rd parties.
        # Workaround: Simply ignore all subsumption edges to "first party" / "third party"        
        for u, v, k in stage2_graph.in_edges(["first party", "third party"], keys=True):
            print(f"Potentially invalid edge: {u} -> {v}")
            edges_to_remove.append((u, v, k))

        # Prevent UNSPECIFIC_* nodes from subsume anything
        for u, v, k in stage2_graph.out_edges(["UNSPECIFIC_DATA", "UNSPECIFIC_ENTITY"], keys=True):
            if k == "SUBSUM":
                edges_to_remove.append((u, v, k))

        stage2_graph.remove_edges_from(edges_to_remove)

        for node in list(stage2_graph.nodes()):
            if stage2_graph.in_degree(node) == stage2_graph.out_degree(node) == 0:
                stage2_graph.remove_node(node)

        return stage2_graph


def trim_graph(graph):
    important_nodes = set()

    for d1, d2, rel in graph.edges(keys=True):
        if rel in ["COLLECT", "NOT_COLLECT"]:
            important_nodes.add(d1)
            important_nodes.add(d2)

    if important_nodes:
        dijkstra_results = nx.multi_source_dijkstra_path_length(graph, important_nodes)
    else:
        dijkstra_results = {}

    important_nodes.update(dijkstra_results.keys())

    useless_nodes = set(graph.nodes) - important_nodes
    returned_graph = graph.copy()
    returned_graph.remove_nodes_from(useless_nodes)

    return returned_graph


def colorize_graph(graph):
    new_graph = nx.MultiDiGraph()

    for label, data in graph.nodes(data=True):
        new_graph.add_node(label, label=label, type=data["type"])

    for i, (u, v, rel, data) in enumerate(graph.edges(keys=True, data=True)):
        new_graph.add_edge(u, v, key=f"e{i}", relationship=rel, text="\n".join(data["text"]))

    return new_graph


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--nlp", required=True, help="NLP model directory")
    parser.add_argument("-p", "--phrase-map", required=True, help="Path to phrase_map.yml")
    parser.add_argument("-e", "--entity-info", required=True, help="Path to entity_info.json")
    parser.add_argument("workdirs", nargs="+", help="Input directories")
    args = parser.parse_args()

    nlp = spacy.load(args.nlp)
    graph_builder = GraphBuilder(args.phrase_map, args.entity_info)

    def gml_stringizer(obj):
        if isinstance(obj, str):
            return obj
        else:
            return json.dumps(obj)

    for d in args.workdirs:
        print(f"Processing {d} ...")

        document = PolicyDocument.load(d, nlp)
        knowledge_graph = graph_builder.build_graph(document)
        #trimmed_graph = trim_graph(knowledge_graph)
        #colored_graph = colorize_graph(trimmed_graph)

        nx.write_gml(knowledge_graph, os.path.join(d, "graph.gml"), stringizer=gml_stringizer)
        #nx.write_gpickle(knowledge_graph, os.path.join(d, "graph.gpickle"))
        #nx.write_gml(trimmed_graph, os.path.join(d, "graph_trimmed.gml"), stringizer=str)
        #nx.write_graphml(colored_graph, os.path.join(d, "graph_trimmed.graphml"))


if __name__ == "__main__":
    main()
