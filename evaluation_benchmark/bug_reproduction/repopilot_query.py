from repopilot import RepoPilot
import os
import argparse
import json
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import re

template = "Please augment the test suite in our Java software. You write a JUnit test case that reproduce the failure behavior of the bug report. {bug_report}"
ROOT_DIR = 'evaluation_benchmark/bug_reproduction/Defects4J/'

def make_input(rep_title, rep_content):
    rep_title = BeautifulSoup(rep_title.strip(), 'html.parser').get_text()
    rep_content = md(rep_content.strip())

    bug_report_content = f"""
    # {rep_title}
    ## Description
    {rep_content}
    """

    return bug_report_content

def load_bug_report(proj, bug_id):
    with open(ROOT_DIR + "bug_report/" + proj + '-' + str(bug_id) + '.json') as f:
        br = json.load(f)
    return make_input(br['title'], br['description'])
    
def query_repopilot_for_gentest(pilot, br):
    output = pilot.query_codebase(template.format(bug_report=br))
    return output 

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--project', default='Time')
    parser.add_argument('-b', '--bug_id', type=int, default=23)
    parser.add_argument('-o', '--out', default='output.txt')
    args = parser.parse_args()
    
    api_key = os.environ.get("OPENAI_API_KEY")
    commit = ""
    repo = f"Defects4J/repos/{args.project}_{args.bug_id}"
    pilot = RepoPilot(repo, commit=commit, openai_api_key=api_key, local=True, language="java", clone_dir="data/repos")
    output = query_repopilot_for_gentest(pilot, load_bug_report(args.project, args.bug_id))