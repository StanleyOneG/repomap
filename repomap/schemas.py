from typing import Dict, List, Optional
from typing_extensions import Annotated
from pydantic import BaseModel, Field, field_validator, PositiveInt, StringConstraints

class MetadataModel(BaseModel):
    """Metadata about the repository."""
    url: Annotated[str, StringConstraints(min_length=1)] = Field(..., description="URL of the repository")
    ref: Annotated[str, StringConstraints(min_length=1)] = Field(..., description="Reference (branch/tag/commit) of the repository")

class FunctionDetailsModel(BaseModel):
    """Details about a function in the AST."""
    name: Annotated[str, StringConstraints(min_length=1)] = Field(..., description="Name of the function")
    start_line: PositiveInt = Field(..., description="Start line of the function definition")
    end_line: PositiveInt = Field(..., description="End line of the function definition")
    class_name: Optional[str] = Field(default=None, alias='class', description="Name of the class if the function is a method, otherwise None")
    calls: List[Annotated[str, StringConstraints(min_length=1)]] = Field(default_factory=list, description="List of function calls within this function")
    is_method: bool = Field(default=False, description="Indicates if the function is a method of a class")

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
    functions: Dict[str, FunctionDetailsModel] = Field(default_factory=dict, description="Dictionary of functions with their details, **keys are function names**")
    classes: Dict[str, ClassDetailsModel] = Field(default_factory=dict, description="Dictionary of classes with their details, **keys are class names**")
    calls: List[CallDetailsModel] = Field(default_factory=list, description="List of function calls in the file")
    imports: List[Annotated[str, StringConstraints(min_length=1)]] = Field(default_factory=list, description="List of imported modules/names in the file")


class FileASTModel(BaseModel):
    """AST and language information for a specific file."""
    language: Annotated[str, StringConstraints(min_length=1)] = Field(..., description="Language of the file")
    ast: ASTModel = Field(..., description="AST representation of the file content")

class RepoStructureModel(BaseModel):
    """Root model representing the entire repository AST structure."""
    metadata: MetadataModel = Field(..., description="Metadata about the repository")
    files: Dict[str, FileASTModel] = Field(..., description="Dictionary of files with their AST representations, **keys are file paths**")