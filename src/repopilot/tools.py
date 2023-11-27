import os
from typing import Type
from pydantic import BaseModel, Field
from langchain.tools import BaseTool, Tool
import jedi
from .llm_multilspy import LSPToolKit
from openai import OpenAI
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.document_loaders.generic import GenericLoader
from langchain.document_loaders.parsers import LanguageParser
from .tree_struct_display import tree
from .llm_multilspy import add_num_line
import numpy as np
from .utils import identify_extension
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores import Chroma

def get_code_jedi(definition, verbose=False):
    raw = definition.get_line_code(after=definition.get_definition_end_position()[0]-definition.get_definition_start_position()[0])
    start_num_line = definition.get_definition_start_position()[0] - 2 # jedi start from 1
    if not verbose:
        return raw
    else:
        results = []
        splited_raw = raw.split("\n")
        for idx, line in enumerate(splited_raw):
            new_line = str(start_num_line + 1) + " " + line
            results.append(new_line)
            start_num_line += 1
        return "\n".join(results)

def search_preliminary_inside_project(names, repo_path, num_result=2, verbose=False, language="python"):
    """Get all matched identifiers from a repo
    
    Args:
        name (str): The name of the identifier
        repo_path (str): The path to the repo
        
    Returns:
        list: A list of matched identifiers
    """
    output_dict = {name: [] for name in names}
    project = jedi.Project(repo_path, environment_path="/datadrive05/huypn16/anaconda3/envs/knn-llm/bin/python3")
    for name in names:
        if not name.endswith(".py"):
            class_definitions = project.search(f"class {name}", all_scopes=True)
            function_definitions = project.search(f"def {name}", all_scopes=True)
            variable_definitions = project.search(name, all_scopes=True)
            idx = 0
            for definition in class_definitions:
                if definition.is_definition():
                    rel_path = os.path.relpath(definition.module_path, repo_path)
                    extracted_definition = {
                        "name": definition.name,
                        "full_name": definition.full_name,
                        "relative_path": rel_path,
                        "documentation": definition._get_docstring(),
                        "implementation": get_code_jedi(definition, verbose)
                    }
                    output_dict[name].append(extracted_definition)
                    idx += 1
                    if idx == num_result:
                        break
            
            idx = 0
            for definition in function_definitions:
                if definition.is_definition():
                    rel_path = os.path.relpath(definition.module_path, repo_path)
                    extracted_definition = {
                        "name": definition.name,
                        "full_name": definition.full_name,
                        "relative_path": rel_path,
                        "documentation": definition._get_docstring(),
                        "implementation": get_code_jedi(definition, verbose),
                    }
                    output_dict[name].append(extracted_definition)
                    idx += 1
                    if idx == num_result:
                        break
            
            idx = 0
            for definition in variable_definitions:
                rel_path = os.path.relpath(definition.module_path, repo_path)
                extracted_definition = {
                    "name": definition.name,
                    "full_name": definition.full_name,
                    "relative_path": rel_path,
                    "documentation": None,
                    "implementation": definition.description,
                }
                output_dict[name].append(extracted_definition)
                idx += 1
                if idx == num_result:
                    break
        else:
            definitions = project.search(name.replace(".py", ""))
            for definition in definitions:
                implementation = ""
                with open(definition.module_path, "r") as f:
                    implementation += f.read()
                extracted_definition = {
                    "name": name,
                    "implementation": implementation
                }
                output_dict[name].append(extracted_definition)
            
    return output_dict

class CodeSearchArgs(BaseModel):
    names: list[str] = Field(..., description="The names of the identifiers to search")

class CodeSearchTool(BaseTool):
    name = "Search Identifiers inside the repo"
    description = """Useful when you want to find all matched identifiers (variable, function, class name) from a python repository, primarily used for class, function search. The results
    are mixed and not sorted by any criteria. So considered using this when you want to find all possible candidates for a given name. Otherwise, consider using other tools for more precise results"""
    args_schema: Type[BaseModel] = CodeSearchArgs
    path = ""
    verbose = False
    language = "python"
    
    def __init__(self, path, language="python"):
        super().__init__()
        self.path = path
        self.language = language
    
    def _run(self, names: list[str], verbose: bool = True):
        return search_preliminary_inside_project(names, repo_path=self.path, verbose=verbose, language=self.language)
    
    def _arun(self, names: list[str], repo_path: str):
        return NotImplementedError("Code Search Tool is not available for async run")

class GoToDefinitionArgs(BaseModel):
    word: str = Field(..., description="The name of the symbol to search")
    line: int = Field(..., description="The line number of the symbol to search")
    relative_path: str = Field(..., description="The relative path of the file containing the symbol to search")
    
class GoToDefinitionTool(BaseTool):
    name = "Go to definition"
    description = """Useful when you want to find the definition of a symbol inside a code snippet if the current context is not cleared enough such as 
    0 import matplotlib.pyplot as plt
    1 class Directory(object):
    2
    3    def add_member(self, id, name):
    4        self.members[id] = plt.figure() we might want to find the definition of plt.figure() invoke with params ("figure", 6, 'test.py')"""
    args_schema = GoToDefinitionArgs
    path = ""
    lsptoolkit: LSPToolKit = None
    language = "python"
    verbose = False
    
    def __init__(self, path, language="python"):
        super().__init__()
        self.path = path
        self.lsptoolkit = LSPToolKit(path, language)
    
    def _run(self, word: str, line: int, relative_path: str):
        return self.lsptoolkit.get_definition(word, relative_path, line, verbose=True)

    def _arun(self, word: str, line: int, relative_path: str):
        return NotImplementedError("Go To Definition Tool is not available for async run")

class FindAllReferencesArgs(BaseModel):
    word: str = Field(..., description="The name of the symbol to find all references")
    line: int = Field(..., description="The line number of the symbol to find all references")
    relative_path: str = Field(..., description="The relative path of the file containing the symbol to find all references")

class FindAllReferencesTool(BaseTool):
    name = "find_all_references"
    description = "Useful when you want to find all references of a symbol inside a code snippet"
    args_schema = FindAllReferencesArgs
    lsptoolkit: LSPToolKit = None
    openai_engine: OpenAI = None
    path = ""
    verbose = False
    language = "python"
    
    def __init__(self, path, language="python"):
        super().__init__()
        self.path = path
        self.lsptoolkit = LSPToolKit(path, language)
        self.openai_engine = OpenAI(api_key="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")
    
    def _run(self, word: str, line: int, relative_path: str, reranking: bool = False, query: str = ""):
        try:
            results = self.lsptoolkit.get_references(word, relative_path, line, verbose=True)
        except FileNotFoundError:
            return "The file is not found, please check the path again, may lack of prefix directory name"
        except IsADirectoryError:
            return "The relative path is a folder, please specify the file path instead. Consider using get_tree_structure to find the file name then use this tool one file path at a time"
        if reranking:
            return self.rerank(results, query)
        else:
            return results[:5]
        
    def _arun(self, word: str, line: int, relative_path: str):
        return NotImplementedError("Find All References Tool is not available for async run")
    
    def rerank(self, results, query):
        reranked_results = []
        for item in results[:20]:
            new_item = {}
            new_item["score"] = self.similarity(query, item)
            new_item["content"] = item
        results = sorted(reranked_results, key=lambda x: x["score"], reverse=True)
        return [item["content"] for item in results[:5]]
    
    def similarity(self, query, implementation):
        embed_query = np.array(self.openai_engine.embeddings.create(input = [query], model=model)['data'][0]['embedding'])
        embed_implementation = np.array(self.openai_engine.create(input=implementation, model="text-embedding-ada-002"))
        score = np.dot(embed_query, embed_implementation) / (np.linalg.norm(embed_query) * np.linalg.norm(embed_implementation))
        return score

class GetAllSymbolsArgs(BaseModel):
    path_to_file: str = Field(..., description="The path of the python file we want extract all symbols from.")
    verbose_level: int = Field(..., description="""verbose_level: efficient verbose settings to save number of tokens. There're 2 levels of details.
                1 - only functions and classes - default
                2 - functions, classes, and methods of classes """)

class GetAllSymbolsTool(BaseTool):
    name = "get_all_symbols"
    description = "Useful when you want to find all symbols (functions, classes, methods) of a python file"
    args_schema = GetAllSymbolsArgs
    lsptoolkit: LSPToolKit = None
    path = ""
    verbose = False
    language = "python"
    
    def __init__(self, path, language="python"):
        super().__init__()
        self.path = path
        self.lsptoolkit = LSPToolKit(path, language)
    
    def _run(self, path_to_file: str, verbose_level: int = 1):
        try:
            return self.lsptoolkit.get_symbols(path_to_file, verbose_level, verbose=True)
        except IsADirectoryError:
            return "The relative path is a folder, please specify the file path instead. Consider using get_tree_structure to find the file name then use this tool one file path at a time"
        except FileNotFoundError:
            return "The file is not found, please check the path again"
        # except:
        #     return "Try to open_file tool to access the file instead"
    
    def _arun(self, relative_path: str):
        return NotImplementedError("Get All Symbols Tool is not available for async run")

class GetTreeStructureArgs(BaseModel):
    relative_path: str = Field(..., description="The relative path of the folder we want to explore")
    level: int = Field(..., description="The level of the tree structure we want to explore, prefer to use 2 (default) for a quick overview of the folder structure then use 3 for more details")

class GetTreeStructureTool(BaseTool):
    name = "get_tree_structure"
    description = """Useful when you want to explore the tree structure of a folder, good for initial exploration with knowing the parent folder name. Remember to provide the relative path correctly.
    Such as if you see and want to explore config folder inside the astropy folder, you should provide the relative path as astropy/config.
    """
    args_schema = GetTreeStructureArgs
    path = ""
    verbose = False
    
    def __init__(self, path):
        super().__init__()
        self.path = path
    
    def _run(self, relative_path: str, level: int = 2):
        abs_path = os.path.join(self.path, relative_path)
        try:
            output = tree(abs_path, level=level)
            output = "The tree structure of " + relative_path + " is: \n" + output
        except: 
            output = "Execution failed, please check the relative path again, likely the relative path lacks of prefix directory name"
        return output
    
    def _arun(self, relative_path: str):
        return NotImplementedError("Get Tree Structure Tool is not available for async run")

class OpenFileArgs(BaseModel):
    relative_file_path: str = Field(..., description="The relative path of the file we want to open")

class OpenFileTool(BaseTool):
    name = "open_file"
    description = """Useful when you want to open a file inside a repo, use this tool only when it's very necessary, usually a main or server or training script. Consider combinining other alternative tools such as GetAllSymbols and CodeSearch to save the number of tokens for other cases."""
    args_schema = OpenFileArgs
    path = ""
    
    def __init__(self, path):
        super().__init__()
        self.path = path
    
    def _run(self, relative_file_path: str):
        abs_path = os.path.join(self.path, relative_file_path)
        try:
            source = open(abs_path, "r").read()
        except FileNotFoundError:
            return "File not found, please check the path again"
        source = add_num_line(source, 0)
        return "The content of " + relative_file_path + " is: \n" + source
    
    def _arun(self, relative_path: str):
        return NotImplementedError("Open File Tool is not available for async run")

class SemanticCodeSearchTool(Tool):
    def __init__(self, path, language="python"):
        """Semantic code search tool allows you to search for code using natural language. It's useful when the query is a sentance, semantic and vague. If exact search such as code search failed after multiple tries, try this

        Args:
            path (_type_): relative path to the repo
            language (str, optional): we have 4 options: python, rust, csharp, java. Defaults to "python".
        """
        extension = identify_extension(language)
        splitter = RecursiveCharacterTextSplitter.from_language(
            language=language, chunk_size=800, chunk_overlap=200
        )

        loader = GenericLoader.from_filesystem(
            path,
            suffixes=[extension],
            parser=LanguageParser(language=language, parser_threshold=500),
        )
        
        documents = loader.load()
        texts = splitter.split_documents(documents)
        self.db = Chroma.from_documents(texts, OpenAIEmbeddings())
        
        def semantic_code_search(query):
            retrieved_docs = self.db.similarity_search(query, k=3)
            return [doc.page_content for doc in retrieved_docs]
        
        super().__init__(
            name="Semantic Code Search",
            func=semantic_code_search,
            description="useful for when the query is a sentance, semantic and vague. If exact search such as code search failed after multiple tries, try this",
        )
        
def main():
    path = "/datadrive05/huypn16/focalcoder/data/repos/repo__astropy__astropy__commit__3832210580d516365ddae1a62071001faf94d416"
    FindAllReferencesTool(path)
    GetAllSymbolsTool(path)