import logging
from typing import Dict, List, Optional
from typing_extensions import Annotated
from pydantic import BaseModel, Field, field_validator, PositiveInt, StringConstraints

logger = logging.getLogger(__name__)

class MetadataModel(BaseModel):
    """Metadata about the repository."""
    url: Annotated[str, StringConstraints(min_length=1)] = Field(..., description="URL of the repository")
    ref: Annotated[str, StringConstraints(min_length=1)] = Field(..., description="Reference (branch/tag/commit) of the repository")

class FunctionCallSiteModel(BaseModel):
    """Details about a specific call site of a function."""
    file_path: str = Field(..., description="Path to the file where the call occurs")
    line_number: PositiveInt = Field(..., description="Line number where the call occurs")
    caller_function_name: Annotated[str, StringConstraints(min_length=1)] = Field(..., description="Name of the function making the call")
    caller_class_name: Optional[str] = Field(default=None, description="Name of the class of the calling function, if applicable")


class FunctionDetailsModel(BaseModel):
    """Details about a function in the AST."""
    name: Annotated[str, StringConstraints(min_length=1)] = Field(..., description="Name of the function")
    start_line: PositiveInt = Field(..., description="Start line of the function definition")
    end_line: PositiveInt = Field(..., description="End line of the function definition")
    class_name: Optional[str] = Field(default=None, alias='class', description="Name of the class if the function is a method, otherwise None")
    calls: List[Annotated[str, StringConstraints(min_length=1)]] = Field(default_factory=list, description="List of function calls within this function")
    is_method: bool = Field(default=False, description="Indicates if the function is a method of a class")
    called_by: List[FunctionCallSiteModel] = Field(default_factory=list, description="List of locations where this function is called in the repository")

    @field_validator("is_method", mode="before")
    @classmethod
    def set_is_method(cls, v: bool, values):
        """Automatically set is_method based on class_name."""
        class_name = values.get("class_name")
        if class_name is not None:
            return True
        return False

    @field_validator("start_line")
    @classmethod
    def validate_start_line(cls, v: int):
        """Ensure start_line is positive."""
        if v <= 0:
            raise ValueError("start_line must be a positive integer")
        return v

    @field_validator("end_line")
    @classmethod
    def validate_end_line_after_start(cls, end_line: int, values):
        """Ensure end_line is not before start_line."""
        start_line = values.get("start_line")
        if start_line is not None and end_line < start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        return end_line

    @property
    def full_name(self) -> str:
        """Fully qualified name including class"""
        return f"{self.class_name}.{self.name}" if self.is_method and self.class_name else self.name


class ClassDetailsModel(BaseModel):
    """Details about a class in the AST."""
    name: Annotated[str, StringConstraints(min_length=1)] = Field(..., description="Name of the class")
    start_line: PositiveInt = Field(..., description="Start line of the class definition")
    end_line: PositiveInt = Field(..., description="End line of the class definition")
    base_classes: List[Annotated[str, StringConstraints(min_length=1)]] = Field(default_factory=list, description="List of base classes")
    methods: List[Annotated[str, StringConstraints(min_length=1)]] = Field(default_factory=list, description="List of method names defined in the class")

    @field_validator("start_line")
    @classmethod
    def validate_start_line(cls, v: int):
        """Ensure start_line is positive."""
        if v <= 0:
            raise ValueError("start_line must be a positive integer")
        return v

    @field_validator("end_line")
    @classmethod
    def validate_end_line_after_start(cls, end_line: int, values):
        """Ensure end_line is not before start_line."""
        start_line = values.get("start_line")
        if start_line is not None and end_line < start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        return end_line


class CallDetailsModel(BaseModel):
    """Details about a function call in the AST."""
    name: Annotated[str, StringConstraints(min_length=1)] = Field(..., description="Name of the called function")
    line: PositiveInt = Field(..., description="Line number where the call occurs")
    caller: Annotated[str, StringConstraints(min_length=1)] = Field(..., description="Name of the function or class method where the call is made")
    class_name: Optional[str] = Field(default=None, alias='class', description="Name of the class if the call is within a class method, otherwise None")

    @field_validator("line")
    @classmethod
    def validate_line(cls, v: int):
        """Ensure line is positive."""
        if v <= 0:
            raise ValueError("line must be a positive integer")
        return v


class ASTModel(BaseModel):
    """Abstract Syntax Tree representation of a file."""
    functions: Dict[str, FunctionDetailsModel] = Field(default_factory=dict, description="Dictionary of functions with their details, keys are function names")
    classes: Dict[str, ClassDetailsModel] = Field(default_factory=dict, description="Dictionary of classes with their details, keys are class names")
    calls: List[CallDetailsModel] = Field(default_factory=list, description="List of function calls in the file")
    imports: List[Annotated[str, StringConstraints(min_length=1)]] = Field(default_factory=list, description="List of imported modules/names in the file")


class FileASTModel(BaseModel):
    """AST and language information for a specific file."""
    language: Annotated[str, StringConstraints(min_length=1)] = Field(..., description="Language of the file")
    ast: ASTModel = Field(..., description="AST representation of the file content")

class RepoStructureModel(BaseModel):
    """Root model representing the entire repository AST structure."""
    metadata: MetadataModel = Field(..., description="Metadata about the repository")
    files: Dict[str, FileASTModel] = Field(..., description="Dictionary of files with their AST representations, keys are file paths")
    _called_by_population_failed: bool = Field(default=False, initvar=False, description="Internal flag to indicate if 'called_by' population failed")

    def model_post_init(self, __context__):
        """Populate cross-reference 'called_by' fields after model initialization with error handling."""
        try:
            populate_function_callers(self)
        except Exception as e:
            logger.error(f"Error populating 'called_by' information: {e}", exc_info=True)
            self._called_by_population_failed = True

    @property
    def is_called_by_population_failed(self) -> bool:
        """Read-only property to check if 'called_by' population failed."""
        return self._called_by_population_failed


def populate_function_callers(repo_structure: RepoStructureModel) -> RepoStructureModel:
    """
    Populates the 'called_by' field in FunctionDetailsModel for each function
    by finding all call sites in the repository.
    Enhanced matching based on function name and class context.
    """
    function_map: Dict[tuple[str, Optional[str]], FunctionDetailsModel] = {} # Key is tuple (function_name, class_name)

    # Create a map of all functions in the repository for efficient lookup by (name, class_name) tuple
    for file_path, file_ast_model in repo_structure.files.items():
        for function_name, function_detail in file_ast_model.ast.functions.items():
            function_map[(function_detail.name, function_detail.class_name)] = function_detail

    # Iterate through all files and calls to find call sites
    for file_path, file_ast_model in repo_structure.files.items():
        for call_detail in file_ast_model.ast.calls:
            called_function_name = call_detail.name
            caller_function_name = call_detail.caller
            caller_class_name = call_detail.class_name

            # Try to match based on function name and class context:
            called_function_details = function_map.get((called_function_name, None)) # Try to find global function first
            if caller_class_name: # If the call is made from within a class method, prioritize class methods
                called_function_details_method = function_map.get((called_function_name, caller_class_name))
                if called_function_details_method:
                    called_function_details = called_function_details_method # Use class method if found

            if called_function_details: # If we found a match (either global or class method)
                call_site = FunctionCallSiteModel(
                    file_path=file_path,
                    line_number=call_detail.line,
                    caller_function_name=caller_function_name,
                    caller_class_name=caller_class_name
                )
                called_function_details.called_by.append(call_site)

    return repo_structure