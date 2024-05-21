# PoliGraph: Automated Privacy Policy Analysis using Knowledge Graphs

PoliGraph is a framework made by UCI Networking Group. This is a fork of their work that is adapted to run on a M1 macbook to work with a dataset of Google Play Store Privacy Policy

This repository hosts the source code for PoliGraph, including:

- PoliGraph-er software - see instructions below.
- Evaluation scripts under `evals/`.
- PoliGraph analysis scripts under `analyses/`.
- Dataset preparation scripts under `datasets/`.
- Model training scripts under `models/`.

PoliGraph is part of [the Policy-Technology project](https://athinagroup.eng.uci.edu/projects/auditing-and-policy-analysis/) of the UCI Networking Group.

## Citation

If you create a publication based on PoliGraph and/or its dataset, please cite the original paper as follows:

```bibtex
@inproceedings{cui2023poligraph,
  title     = {{PoliGraph: Automated Privacy Policy Analysis using Knowledge Graphs}},
  author    = {Cui, Hao and Trimananda, Rahmadi and Markopoulou, Athina and Jordan, Scott},
  booktitle = {Proceedings of the 32nd USENIX Security Symposium (USENIX Security 23)},
  year      = {2023}
}
```

## System Requirements

I am currently testing all the code in this repository on a M1 Macbook with the following configuration:
- CPU: M1 Max
- Memory: 64 GiB
- OS: macOS Sonoma 14.6

## PoliGraph-er

PoliGraph-er is the NLP software used to generate PoliGraphs from the text of a privacy policy.

### Installation

PoliGraph-er is written in Python. The original repo suggests using Conda, however this repo uses pip instead.

Create a virtual environment using venv and activate it:
```sh
$ python3 -m venv venv
$ source ./venv/bin/activate
```

After cloning this repository and creating a virtual environment, change the working directory to the cloned directory.

Install the necessary pip packages using:
```sh
$ pip install -r requirements.txt
```

Initialize the Playwright library (used by the crawler script):

```sh
$ playwright install
```

Download `poligrapher-extra-data.tar.gz` from [here](https://drive.google.com/file/d/1qHifRx93EfTkg2x1e2W_lgQAgk7HcXhP/view?usp=sharing). Extract its content to `poligrapher/extra-data`:

```sh
$ tar xf /path/to/poligrapher-extra-data.tar.gz -C poligrapher/extra-data
```

Download the PrivacyPoliciesDataset_Brianna dataset from [here](example.html). Extract its content to `PrivacyPoliciesDataset_Brianna`.

Install the PoliGraph-er (`poligrapher`) library:

```sh
$ pip install --editable .
```

### Basic Usage

Here we illustrate how to generate a PoliGraph from a real privacy policy. We use the following privacy policy webpage as an example:

```sh
$ POLICY_URL="https://web.archive.org/web/20230330161225id_/https://proteygames.github.io/"
```

First, run the HTML crawler script to download the webpage:

```sh
$ python -m poligrapher.scripts.html_crawler ${POLICY_URL} example/
```

The directory `example/` will be used to store all the intermediate and final output associated with this privacy policy.

Second, run the `init_document` script to preprocess the webpage and run the NLP pipeline on the privacy policy document:

```sh
$ python -m poligrapher.scripts.init_document example/
```

Third, execute the `run_annotators` script to run annotators on the privacy policy document.

```sh
$ python -m poligrapher.scripts.run_annotators example/
```

Lastly, execute the `build_graph` script to generate the PoliGraph:

```sh
$ python -m poligrapher.scripts.build_graph example/
```

The generated graph is stored at `example/graph-original.yml`. You may use a text editor to view it. The format is human-readable and fairly straightforward.

Alternatively, if you run `build_graph` with the `--pretty` parameter, it will generate a PoliGraph in the GraphML format (`example/graph-original.graphml`), which can be imported to some graph editor software:

```sh
$ python -m poligrapher.scripts.build_graph --pretty example/
```

For more instructions on how to view the graphs, please refer to the document [Viewing a PoliGraph](./docs/view-poligraph.md).

### Batch Processing

The `init_document`, `run_annotators`, and `build_graph` scripts support batch processing. Simply supply multiple directories in the arguments:

```sh
$ python -m poligrapher.scripts.init_document dataset/policy1 dataset/policy2 dataset/policy3
$ python -m poligrapher.scripts.run_annotators dataset/policy1 dataset/policy2 dataset/policy3
$ python -m poligrapher.scripts.build_graph dataset/policy1 dataset/policy2 dataset/policy3
```

If all the subdirectories under `dataset` contain valid crawled webpages, you may simply supply `dataset/*` to let the shell expand the arguments.


## Artifact Evaluation

We will update the documentation under the `docs/` directory to explain the usage of other scripts.

Please refer to the document [USENIX Security 2023 Artifact Evaluation](./docs/usenix-artifact-evaluation.md) and [Artifact Evaluation (Additional Experiments)](./docs/usenix-artifact-evaluation-additional.md) for instructions on reproducing the main results in the original paper.

## Usage with the Brianna Dataset

To use this with the Brianna dataset, simply run the command below
```sh
$ python3 briannaRun.py
```

Output graphs will be saved to the `output/{filename}` directory, and the graphs stored within will be fed into Neo4J.

