(class_definition
  name: (identifier) @name.definition.class) @definition.class

(function_definition
  name: (identifier) @name.definition.function) @definition.function

(call
  function: [
    (identifier) @name.reference.call
    (attribute
      object: (_)* @obj
      attribute: (identifier) @name.reference.call
    ) 
  ]) @reference.call
