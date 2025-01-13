(struct_specifier name: (type_identifier) @name.definition.class body:(_)) @definition.class

(declaration type: (union_specifier name: (type_identifier) @name.definition.class)) @definition.class

(function_declarator declarator: (identifier) @name.definition.function) @definition.function

(type_definition declarator: (type_identifier) @name.definition.type) @definition.type

(enum_specifier name: (type_identifier) @name.definition.type) @definition.type

; Add patterns for capturing function calls
(call_expression
  function: (identifier) @name.reference.call)

(call_expression
  function: (field_expression
    field: (field_identifier) @name.reference.call))
