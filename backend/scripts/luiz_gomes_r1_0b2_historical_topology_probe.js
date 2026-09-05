(() => {
  const d = db.getSiblingDB("sigesc");
  const PREFIX = "LUIZ_GOMES_F6_3C_POINT_JSON=";
  const TEACHER = "Luiz Gomes dos Santos";
  const MATH = "Matemática";
  const ROLES = ["6º ANO A", "6º ANO B", "7º ANO A", "7º ANO B", "8º ANO A", "9º ANO A"];
  const START = "2026-02-01";
  const END = "2026-05-01";
  const SKIP_KEYS = new Set([
    "content", "methodology", "observations", "resources", "records",
    "students", "student", "grades", "notes", "password", "token",
    "refresh_token", "access_token", "email", "phone", "telefone", "cpf",
    "nis", "address", "endereco", "birth_date", "date_of_birth"
  ]);

  const sid = (v) => {
    if (v === null || v === undefined) return "";
    if (typeof v === "object" && typeof v.valueOf === "function") {
      try {
        const x = v.valueOf();
        if (x !== v && x !== null && x !== undefined) return String(x).trim();
      } catch (_) {}
    }
    return String(v).trim();
  };
  const norm = (v) => sid(v).normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR")
    .replace(/\s+/g, " ").trim();
  const scalar = (v) => v === null || v === undefined || ["string", "number", "boolean"].includes(typeof v) ||
    (typeof v === "object" && typeof v.valueOf === "function" && v.valueOf() !== v);
  const leaves = (obj, prefix = "", depth = 0, out = []) => {
    if (!obj || typeof obj !== "object" || depth > 4) return out;
    for (const [key, value] of Object.entries(obj)) {
      if (SKIP_KEYS.has(String(key).toLocaleLowerCase("pt-BR"))) continue;
      const path = prefix ? `${prefix}.${key}` : key;
      if (Array.isArray(value)) {
        for (const item of value.slice(0, 64)) {
          if (scalar(item)) out.push([`${path}[]`, sid(item)]);
          else leaves(item, `${path}[]`, depth + 1, out);
        }
      } else if (scalar(value)) out.push([path, sid(value)]);
      else leaves(value, path, depth + 1, out);
    }
    return out;
  };
  const vals = (doc) => [...new Set(leaves(doc).map(([, v]) => v).filter(Boolean))];
  const paths = (docs) => [...new Set(docs.flatMap((doc) => leaves(doc).map(([p]) => p)))];
  const inPeriod = (v) => {
    const s = sid(v).slice(0, 10);
    return /^\d{4}-\d{2}-\d{2}$/.test(s) && s >= START && s < END;
  };
  const payloadPresent = (row) => ["content", "methodology", "observations", "resources"].some((k) => {
    const v = row && row[k];
    if (Array.isArray(v)) return v.length > 0;
    if (v && typeof v === "object") return Object.keys(v).length > 0;
    return sid(v) !== "";
  });
  const generic = (v) => {
    const n = norm(v);
    if (!n) return true;
    if (["true", "false", "active", "inactive", "ativo", "inativo", "2026"].includes(n)) return true;
    if (/^\d{4}-\d{2}-\d{2}/.test(n)) return true;
    if (/^\d+$/.test(n) && n.length <= 4) return true;
    return false;
  };
  const intersects = (a, b) => {
    const set = b instanceof Set ? b : new Set(b);
    return a.some((v) => set.has(v));
  };
  const fnv = (text, seed) => {
    let h = seed >>> 0;
    for (let i = 0; i < text.length; i += 1) {
      h ^= text.charCodeAt(i);
      h = Math.imul(h, 16777619) >>> 0;
    }
    return h.toString(16).padStart(8, "0");
  };
  const fingerprint = (text) => `${fnv(text, 2166136261)}${fnv(text.split("").reverse().join(""), 2246822519)}`;

  const boundaries = {
    source_dump_read_only: true,
    temporary_mongo_network_none: true,
    production_writes: false,
    student_data_read: false,
    attendance_read: false,
    attendance_records_read: false,
    grades_read: false,
    pedagogical_plaintext_emitted: false,
    technical_ids_emitted: false,
    actor_payload_attribution_attempted: false,
    current_ids_used_for_mapping: false,
    class_labels_used_for_mapping: false,
    fail_closed_on_ambiguity: true,
    fail_closed_on_graph_symmetry: true
  };
  const emit = (status, classification, extra = {}) => print(PREFIX + JSON.stringify(Object.assign({
    schema: "LUIZ_GOMES_R1_0B2_HISTORICAL_TOPOLOGY_V1",
    status,
    overall_classification: classification,
    source_date: "2026-08-18",
    period: { from: START, to_exclusive: END },
    boundaries
  }, extra)));
  const inconclusive = (reason, extra = {}) => emit("INCONCLUSIVE", "HISTORICAL_TOPOLOGY_BRIDGE_INCONCLUSIVE", Object.assign({
    insufficiency_reason: reason,
    next_gate_r1_0c_open: false
  }, extra));

  const names = d.getCollectionNames();
  const required = ["classes", "courses", "learning_objects"];
  const missing = required.filter((x) => !names.includes(x));
  if (missing.length) {
    inconclusive("REQUIRED_COLLECTION_MISSING", { missing_collection_count: missing.length });
    return;
  }
  const assignmentCollections = ["teacher_assignments", "teacher_class_assignments"].filter((x) => names.includes(x));
  if (!assignmentCollections.length) {
    inconclusive("ASSIGNMENT_COLLECTION_MISSING");
    return;
  }
  const identityCollections = ["users", "staff"].filter((x) => names.includes(x));
  if (!identityCollections.length) {
    inconclusive("IDENTITY_COLLECTION_MISSING");
    return;
  }

  const classDocs = d.classes.find({}).toArray();
  const courseDocs = d.courses.find({}).toArray();
  const loDocs = d.learning_objects.find({}).toArray();
  const contentDocs = names.includes("content_entries") ? d.content_entries.find({}).toArray() : [];
  const assignmentDocs = assignmentCollections.flatMap((collection) =>
    d.getCollection(collection).find({}).toArray().map((doc) => ({ collection, doc }))
  );
  const identityDocs = identityCollections.flatMap((collection) =>
    d.getCollection(collection).find({}).toArray().map((doc) => ({ collection, doc }))
  );

  if (!classDocs.length || !courseDocs.length || !assignmentDocs.length) {
    inconclusive("REQUIRED_TOPOLOGY_EMPTY", {
      class_docs: classDocs.length,
      course_docs: courseDocs.length,
      assignment_docs: assignmentDocs.length
    });
    return;
  }

  // Atores: o nome é usado apenas para localizar o nó histórico do professor. O bridge de turma
  // é feito pelas arestas de assignments; nenhum ID atual é consultado ou comparado.
  const identityValueSets = identityDocs.map(({ doc }) => new Set(vals(doc).filter((v) => !generic(v))));
  const identityValueFrequency = new Map();
  identityValueSets.forEach((set) => set.forEach((v) =>
    identityValueFrequency.set(v, (identityValueFrequency.get(v) || 0) + 1)
  ));
  const teacherSeedIndexes = identityDocs.map(({ doc }, i) =>
    leaves(doc).some(([, v]) => norm(v) === norm(TEACHER)) ? i : -1
  ).filter((i) => i >= 0);
  if (!teacherSeedIndexes.length) {
    inconclusive("HISTORICAL_TEACHER_VALUE_NOT_RESOLVED", { teacher_value_matches: 0 });
    return;
  }
  // Expande o componente histórico do ator por valores compartilhados (ex.: users.id ↔ staff.user_id),
  // sem assumir aliases. O componente é interno e seus valores nunca são externalizados.
  const teacherComponent = new Set(teacherSeedIndexes);
  let changed = true;
  while (changed) {
    changed = false;
    const componentValues = new Set([...teacherComponent]
      .flatMap((i) => [...identityValueSets[i]])
      .filter((v) => (identityValueFrequency.get(v) || 0) <= 2));
    identityValueSets.forEach((set, i) => {
      if (teacherComponent.has(i)) return;
      if ([...set].some((v) => componentValues.has(v) && (identityValueFrequency.get(v) || 0) <= 2)) {
        teacherComponent.add(i);
        changed = true;
      }
    });
  }
  const outsideIdentityValues = new Set(identityValueSets.filter((_, i) => !teacherComponent.has(i)).flatMap((set) => [...set]));
  const teacherIdentityValues = new Set([...teacherComponent]
    .flatMap((i) => [...identityValueSets[i]])
    .filter((v) => norm(v) !== norm(TEACHER) && !generic(v) && !outsideIdentityValues.has(v)));
  if (!teacherIdentityValues.size) {
    inconclusive("HISTORICAL_TEACHER_RELATIONAL_IDENTITY_NOT_RESOLVED", {
      teacher_value_matches: teacherSeedIndexes.length,
      teacher_identity_component_docs: teacherComponent.size
    });
    return;
  }

  const assignmentValueSets = assignmentDocs.map(({ doc }) => new Set(vals(doc)));
  const teacherAssignmentIndexes = new Set();
  assignmentValueSets.forEach((set, i) => {
    if ([...teacherIdentityValues].some((v) => set.has(v))) teacherAssignmentIndexes.add(i);
  });
  if (!teacherAssignmentIndexes.size) {
    inconclusive("TEACHER_ASSIGNMENT_NEIGHBORHOOD_EMPTY", { teacher_value_matches: teacherSeedIndexes.length, teacher_identity_component_docs: teacherComponent.size });
    return;
  }

  // Matemática: resolve valores relacionais exclusivos dos documentos de curso Matemática.
  const mathDocs = courseDocs.filter((doc) => leaves(doc).some(([, v]) => norm(v) === norm(MATH)));
  if (!mathDocs.length) {
    inconclusive("MATH_COURSE_VALUE_NOT_RESOLVED");
    return;
  }
  const nonMathValues = new Set(courseDocs.filter((doc) => !mathDocs.includes(doc)).flatMap(vals));
  const mathIdentityValues = new Set(mathDocs.flatMap(vals)
    .filter((v) => norm(v) !== norm(MATH) && !generic(v) && !nonMathValues.has(v)));
  if (!mathIdentityValues.size) {
    inconclusive("MATH_RELATIONAL_IDENTITY_NOT_RESOLVED", { math_course_docs: mathDocs.length });
    return;
  }

  const teacherMathAssignmentIndexes = new Set([...teacherAssignmentIndexes].filter((i) =>
    [...mathIdentityValues].some((v) => assignmentValueSets[i].has(v))
  ));
  if (!teacherMathAssignmentIndexes.size) {
    inconclusive("TEACHER_MATH_ASSIGNMENT_NEIGHBORHOOD_EMPTY", {
      teacher_assignment_count: teacherAssignmentIndexes.size,
      math_course_docs: mathDocs.length
    });
    return;
  }

  // Para cada classe, retém apenas valores escalares exclusivos daquele documento. A decisão
  // não conhece o significado do valor e nunca o externaliza; ele funciona somente como aresta.
  const classValues = classDocs.map(vals);
  const classValueFrequency = new Map();
  classValues.forEach((arr) => new Set(arr.filter((v) => !generic(v))).forEach((v) =>
    classValueFrequency.set(v, (classValueFrequency.get(v) || 0) + 1)
  ));
  const classUniqueValues = classValues.map((arr) => new Set(arr.filter((v) => !generic(v) && classValueFrequency.get(v) === 1)));

  const mapAssignmentToClasses = (assignmentIndex) => {
    const set = assignmentValueSets[assignmentIndex];
    const hits = [];
    classUniqueValues.forEach((uniqueSet, classIndex) => {
      if ([...uniqueSet].some((v) => set.has(v))) hits.push(classIndex);
    });
    return hits;
  };
  const teacherMathClassIndexes = new Set();
  for (const i of teacherMathAssignmentIndexes) {
    const hits = mapAssignmentToClasses(i);
    if (hits.length !== 1) {
      inconclusive("ASSIGNMENT_CLASS_EDGE_AMBIGUOUS", {
        teacher_math_assignment_count: teacherMathAssignmentIndexes.size,
        ambiguous_edge_candidate_count: hits.length
      });
      return;
    }
    teacherMathClassIndexes.add(hits[0]);
  }

  if (teacherMathClassIndexes.size !== 6) {
    inconclusive("LUIZ_MATH_SIX_NODE_NEIGHBORHOOD_NOT_RESOLVED", {
      teacher_assignment_count: teacherAssignmentIndexes.size,
      teacher_math_assignment_count: teacherMathAssignmentIndexes.size,
      candidate_class_node_count: teacherMathClassIndexes.size
    });
    return;
  }

  const courseValues = courseDocs.map(vals);
  const courseValueFrequency = new Map();
  courseValues.forEach((arr) => new Set(arr.filter((v) => !generic(v))).forEach((v) =>
    courseValueFrequency.set(v, (courseValueFrequency.get(v) || 0) + 1)
  ));
  const courseUniqueValues = courseValues.map((arr) => new Set(arr.filter((v) => !generic(v) && courseValueFrequency.get(v) === 1)));
  const assignmentCourses = assignmentValueSets.map((set) => {
    const hits = [];
    courseUniqueValues.forEach((u, idx) => { if ([...u].some((v) => set.has(v))) hits.push(idx); });
    return hits;
  });

  const loValueSets = loDocs.map((doc) => new Set(vals(doc)));
  const contentValueSets = contentDocs.map((doc) => new Set(vals(doc)));
  const datePaths = paths(loDocs).filter((p) => loDocs.some((doc) => leaves(doc).some(([path, v]) => path === p && inPeriod(v))));
  const loDates = (doc) => leaves(doc).filter(([, v]) => inPeriod(v)).map(([, v]) => sid(v).slice(0, 10));

  const anonymous = [];
  for (const classIndex of [...teacherMathClassIndexes]) {
    const classRefs = classUniqueValues[classIndex];
    const incidentAssignments = assignmentValueSets.map((set, i) => intersects([...classRefs], set) ? i : -1).filter((i) => i >= 0);
    const incidentCourseIndexes = new Set(incidentAssignments.flatMap((i) => assignmentCourses[i]));
    const incidentLO = loValueSets.map((set, i) => intersects([...classRefs], set) ? i : -1).filter((i) => i >= 0);
    const mathLO = incidentLO.filter((i) => [...mathIdentityValues].some((v) => loValueSets[i].has(v)));
    const mathPeriodLO = mathLO.filter((i) => loDates(loDocs[i]).length > 0);
    const distinctDates = new Set(mathPeriodLO.flatMap((i) => loDates(loDocs[i])));
    const incidentContent = contentValueSets.map((set, i) => intersects([...classRefs], set) ? i : -1).filter((i) => i >= 0);
    const teacherMathAssignmentsForNode = incidentAssignments.filter((i) => teacherMathAssignmentIndexes.has(i));
    const signatureObject = {
      assignment_degree: incidentAssignments.length,
      course_degree: incidentCourseIndexes.size,
      learning_object_degree: incidentLO.length,
      math_learning_object_degree: mathLO.length,
      math_rows_in_period: mathPeriodLO.length,
      distinct_math_dates_in_period: distinctDates.size,
      payload_rows_in_period: mathPeriodLO.filter((i) => payloadPresent(loDocs[i])).length,
      content_entry_degree: incidentContent.length,
      teacher_math_assignment_degree: teacherMathAssignmentsForNode.length
    };
    const signature = JSON.stringify(signatureObject);
    anonymous.push({ classIndex, signature, topology_fingerprint: fingerprint(signature), ...signatureObject });
  }

  const topologyGroups = new Map();
  anonymous.forEach((node) => {
    if (!topologyGroups.has(node.signature)) topologyGroups.set(node.signature, []);
    topologyGroups.get(node.signature).push(node);
  });
  const symmetricGroups = [...topologyGroups.values()].filter((g) => g.length > 1);
  const sanitizedNodes = anonymous
    .map(({ classIndex, signature, ...safe }) => safe)
    .sort((a, b) => a.topology_fingerprint.localeCompare(b.topology_fingerprint));

  if (symmetricGroups.length) {
    emit("INCONCLUSIVE", "HISTORICAL_TOPOLOGY_BRIDGE_SYMMETRIC", {
      insufficiency_reason: "GRAPH_AUTOMORPHISM_OR_EQUAL_LOCAL_SIGNATURE",
      topology_bridge: {
        selected: false,
        six_node_neighborhood_resolved: true,
        candidate_class_node_count: 6,
        distinct_topology_signature_count: topologyGroups.size,
        symmetric_group_count: symmetricGroups.length,
        role_mapping_resolved: false,
        role_mapping_reason: "SYMMETRIC_ANONYMOUS_CLASS_NODES"
      },
      anonymous_nodes: sanitizedNodes,
      date_path_candidate_count: datePaths.length,
      next_gate_r1_0c_open: false
    });
    return;
  }

  // Mesmo seis assinaturas diferentes não dão nomes pedagógicos aos nós. Sem âncora semântica
  // independente no próprio grafo, uma bijeção para ROLES seria arbitrária. Não inventar.
  inconclusive("SIX_NODE_NEIGHBORHOOD_RESOLVED_ROLE_MAPPING_UNANCHORED", {
    topology_bridge: {
      selected: false,
      six_node_neighborhood_resolved: true,
      candidate_class_node_count: 6,
      distinct_topology_signature_count: topologyGroups.size,
      symmetric_group_count: 0,
      role_mapping_resolved: false,
      required_role_count: ROLES.length,
      role_mapping_reason: "NO_INDEPENDENT_SEMANTIC_ROLE_ANCHOR"
    },
    anonymous_nodes: sanitizedNodes,
    date_path_candidate_count: datePaths.length,
    next_gate_r1_0c_open: false
  });
})();
