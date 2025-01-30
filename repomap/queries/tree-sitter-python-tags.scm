(class_definition
  name: (identifier) @name.definition.class) @definition.class

(function_definition
  name: (identifier) @name.definition.function) @definition.function

(call
  function: [
    (identifier) @name.reference.call
    (attribute
      object: (_) @name.ref.obj
      attribute: (identifier) @name.ref.attr
    ) @name.reference.call
  ]) @reference.call

(assignment
  left: (identifier) @variable.name
  right: (call
    function: (identifier) @function.name
  ) @variable.assign.call) @assignment
