anchor: pass:flatten

`flatten` copies each instance's body into the module that holds it, following the instance
tree top-down. The log says `3 instances to expand`, then one line per instance path; the
copied objects are dotted (`two.count`, `gate.y`) and keep a DERIVED provenance record, so
the hierarchy can be recovered after flattening.

The log also names the modules no longer instantiated (`counter`, `counter$WIDTH=4`,
`and_gate`). The IR cannot remove modules, so they remain in the snapshot but nothing
instantiates them: the live design is the flat top from here on, which is why `opt`, `lower`
and ABC work on one module.
