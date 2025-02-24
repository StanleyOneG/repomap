(struct_specifier
  name: (type_identifier) @name_definition_class
  body: (_)) @definition_class

(declaration
  type: (union_specifier
    name: (type_identifier) @name_definition_class)) @definition_class

(function_declarator
  declarator: (identifier) @name_definition_function) @definition_function

(function_declarator
  declarator: (field_identifier) @name_definition_function) @definition_function

(function_declarator
  declarator: (qualified_identifier) @name_definition_method) @definition_method

(type_definition
  declarator: (type_identifier) @name_definition_type) @definition_type

(enum_specifier
  name: (type_identifier) @name_definition_type) @definition_type

(class_specifier
  name: (type_identifier) @name_definition_class) @definition_class

(call_expression
  function: [
    (identifier) @name.reference.call
    (field_expression
      field: (field_identifier) @name.reference.call)
    (qualified_identifier) @name.reference.call
  ])
