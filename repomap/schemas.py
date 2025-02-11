import logging
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, NonNegativeInt, StringConstraints, computed_field
from typing_extensions import Annotated

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class MetadataModel(BaseModel):
    """Metadata about the repository."""

    url: Annotated[str, StringConstraints(min_length=1)] = Field(
        ..., description="URL of the repository"
    )
    ref: Annotated[str, StringConstraints(min_length=1)] = Field(
        ..., description="Reference (branch/tag/commit) of the repository"
    )


class FunctionCallSiteModel(BaseModel):
    """Details about a specific call site of a function."""

    file_path: str = Field(..., description="Path to the file where the call occurs")
    line_number: NonNegativeInt = Field(
        ..., description="Line number where the call occurs"
    )
    caller_function_name: Annotated[str, StringConstraints(min_length=1)] = Field(
        ..., description="Name of the function making the call"
    )
    caller_class_name: Optional[str] = Field(
        default=None,
        description="Name of the class of the calling function, if applicable",
    )


class FunctionDetailsModel(BaseModel):
    """Details about a function in the AST."""

    name: Annotated[str, StringConstraints(min_length=1)] = Field(
        ..., description="Name of the function"
    )
    start_line: NonNegativeInt = Field(
        ..., description="Start line of the function definition"
    )
    end_line: NonNegativeInt = Field(
        ..., description="End line of the function definition"
    )
    class_name: Optional[str] = Field(
        default=None,
        validation_alias="class",
        description="Name of the class if the function is a method, otherwise None",
    )
    calls: List[Annotated[str, StringConstraints(min_length=1)]] = Field(
        default_factory=list, description="List of function calls within this function"
    )
    called_by: List[FunctionCallSiteModel] = Field(
        default_factory=list,
        description="List of locations where this function is called in the repository",
    )

    @computed_field
    @property
    def is_method(self) -> bool:
        """Automatically set is_method based on class_name."""
        class_name = self.class_name
        return class_name is not None

    @property
    def full_name(self) -> str:
        """Fully qualified name including class"""
        return (
            f"{self.class_name}.{self.name}"
            if self.is_method and self.class_name
            else self.name
        )


class ClassDetailsModel(BaseModel):
    """Details about a class in the AST."""

    name: Annotated[str, StringConstraints(min_length=1)] = Field(
        ..., description="Name of the class"
    )
    start_line: NonNegativeInt = Field(
        ..., description="Start line of the class definition"
    )
    end_line: NonNegativeInt = Field(
        ..., description="End line of the class definition"
    )
    base_classes: List[Annotated[str, StringConstraints(min_length=1)]] = Field(
        default_factory=list, description="List of base classes"
    )
    methods: List[Annotated[str, StringConstraints(min_length=1)]] = Field(
        default_factory=list, description="List of method names defined in the class"
    )


class CallDetailsModel(BaseModel):
    """Details about a function call in the AST."""

    name: Annotated[str, StringConstraints(min_length=1)] = Field(
        ..., description="Name of the called function"
    )
    line: NonNegativeInt = Field(..., description="Line number where the call occurs")
    caller: Annotated[str, StringConstraints(min_length=1)] = Field(
        ..., description="Name of the function or class method where the call is made"
    )
    class_name: Optional[str] = Field(
        default=None,
        alias='class',
        description="Name of the class if the call is within a class method, otherwise None",
    )


class ASTModel(BaseModel):
    """Abstract Syntax Tree representation of a file."""

    functions: Dict[str, FunctionDetailsModel] = Field(
        default_factory=dict,
        description="Dictionary of functions with their details, keys are function names",
    )
    classes: Dict[str, ClassDetailsModel] = Field(
        default_factory=dict,
        description="Dictionary of classes with their details, keys are class names",
    )
    calls: List[CallDetailsModel] = Field(
        default_factory=list, description="List of function calls in the file"
    )
    imports: List[Annotated[str, StringConstraints(min_length=1)]] = Field(
        default_factory=list, description="List of imported modules/names in the file"
    )


class FileASTModel(BaseModel):
    """AST and language information for a specific file."""

    language: Annotated[str, StringConstraints(min_length=1)] = Field(
        ..., description="Language of the file"
    )
    ast: ASTModel = Field(..., description="AST representation of the file content")


class RepoStructureModel(BaseModel):
    """Root model representing the entire repository AST structure."""

    metadata: MetadataModel = Field(..., description="Metadata about the repository")
    files: Dict[str, FileASTModel] = Field(
        ...,
        description="Dictionary of files with their AST representations, keys are file paths",
    )
    is_called_by_population_failed: Optional[bool] = Field(
        default=None,
        initvar=False,
        description="Internal flag to indicate if 'called_by' population failed",
    )

    def model_post_init(self, __context__):
        """Populate cross-reference 'called_by' fields after model initialization with error handling."""
        try:
            populate_function_callers(self)
            self.is_called_by_population_failed = False
        except Exception:
            self.is_called_by_population_failed = True


def populate_function_callers(repo_structure: RepoStructureModel) -> RepoStructureModel:
    """
    Populates the 'called_by' field in FunctionDetailsModel for each function
    by finding all call sites in the repository.
    """
    function_map: Dict[str, FunctionDetailsModel] = {}

    # Create a map of all functions in the repository for easy lookup by full_name
    for file_path, file_ast_model in repo_structure.files.items():
        for function_name, function_detail in file_ast_model.ast.functions.items():
            function_map[function_detail.full_name] = function_detail

    # Iterate through all files and calls to find call sites
    for file_path, file_ast_model in repo_structure.files.items():
        for call_detail in file_ast_model.ast.calls:
            called_function_name = call_detail.name  # Name of the function being called
            caller_function_name = (
                call_detail.caller
            )  # Name of the function making the call
            caller_class_name = call_detail.class_name

            # Check if the called function exists in our function_map (defined in the repository)
            if called_function_name in function_map:

                call_site = FunctionCallSiteModel(
                    file_path=file_path,
                    line_number=call_detail.line,
                    caller_function_name=caller_function_name,
                    caller_class_name=caller_class_name,
                )
                # Get the FunctionDetailsModel of the function being called and append the call site
                function_map[called_function_name].called_by.append(call_site)

    return repo_structure
