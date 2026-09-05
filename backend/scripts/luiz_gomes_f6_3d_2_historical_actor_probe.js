(() => {
  const d = db.getSiblingDB("sigesc");
  const PREFIX = "LUIZ_GOMES_F6_3C_POINT_JSON=";
  const CONTROLS = ["6º ANO A", "6º ANO B", "7º ANO A", "7º ANO B"];
  const TARGETS = ["8º ANO A", "9º ANO A"];
  const ALL_CLASSES = [...CONTROLS, ...TARGETS];
  const START = "2026-02-01";
  const END = "2026-05-01";

  const CLASS_NAME_KEYS = ["name", "nome", "class_name", "turma", "turma_nome", "label"];
  const CLASS_ID_KEYS = ["id", "_id", "class_id", "turma_id", "uuid", "code"];
  const CLASS_GROUP_KEYS = ["school_id", "escola_id", "schoolId", "school", "school_uuid", "school_unit_id", "unit_id", "mantenedora_id", "tenant_id"];
  const CLASS_YEAR_KEYS = ["academic_year", "ano_letivo", "school_year", "year", "ano"];

  const COURSE_NAME_KEYS = ["name", "nome", "course_name", "component_name", "disciplina", "label"];
  const COURSE_ID_KEYS = ["id", "_id", "course_id", "component_id", "uuid", "code"];

  const LO_CLASS_KEYS = ["class_id", "turma_id", "classId", "class", "class_uuid"];
  const LO_COURSE_KEYS = ["course_id", "component_id", "disciplina_id", "courseId", "componentId"];
  const LO_DATE_KEYS = ["date", "data", "lesson_date", "data_aula", "class_date"];
  const ACTOR_FIELDS = ["recorded_by", "created_by", "updated_by", "teacher_id", "staff_id", "professor_id", "user_id", "actor_id"];

  const ASSIGN_CLASS_KEYS = ["class_id", "turma_id", "classId"];
  const ASSIGN_COURSE_KEYS = ["course_id", "component_id", "disciplina_id", "courseId", "componentId"];
  const ASSIGN_STAFF_KEYS = ["staff_id", "teacher_id", "professor_id", "user_id"];
  const ASSIGN_YEAR_KEYS = ["academic_year", "ano_letivo", "school_year", "year", "ano"];
  const ASSIGN_STATUS_KEYS = ["status", "state", "situacao"];

  const sid = (v) => {
    if (v === null || v === undefined) return "";
    if (typeof v === "object" && typeof v.valueOf === "function") {
      try {
        const value = v.valueOf();
        if (value !== v && value !== null && value !== undefined) return String(value).trim();
      } catch (_) {}
    }
    return String(v).trim();
  };
  const norm = (v) => sid(v)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR")
    .replace(/º/g, "o")
    .replace(/ª/g, "a")
    .replace(/\s+/g, " ")
    .trim();
  const get = (obj, path) => {
    if (!obj) return undefined;
    if (path === "_id") return obj._id;
    const parts = String(path).split(".");
    let cur = obj;
    for (const part of parts) {
      if (cur === null || cur === undefined || typeof cur !== "object" || !(part in cur)) return undefined;
      cur = cur[part];
    }
    return cur;
  };
  const exists = (name) => d.getCollectionNames().includes(name);
  const inPeriod = (v) => {
    const s = sid(v).slice(0, 10);
    return s >= START && s < END;
  };
  const payload = (r) => Boolean(sid(r.content) || sid(r.methodology) || sid(r.observations));
  const safeObserved = (docs, keys) => keys.filter((key) => docs.some((doc) => sid(get(doc, key)) !== ""));
  const unique = (values) => [...new Set(values)];

  const baseBoundaries = {
    actor_identity_derived_without_user_lookup: true,
    technical_ids_emitted: false,
    pedagogical_plaintext_emitted: false,
    pedagogical_payload_boolean_only: true,
    attendance_records_read: false,
    student_data_read: false,
    production_writes: false,
    schema_aliases_fail_closed: true,
  };

  const emit = (status, classification, extra = {}) => print(PREFIX + JSON.stringify(Object.assign({
    schema: "LUIZ_GOMES_F6_3D_2_HISTORICAL_ACTOR_V3_ADAPTIVE",
    status,
    overall_classification: classification,
    source_date: "2026-08-18",
    period: { from: START, to_exclusive: END },
    boundaries: baseBoundaries,
  }, extra)));

  const insufficient = (reason, diagnostics = {}) => {
    emit("INCONCLUSIVE", "HISTORICAL_SCHEMA_INSUFFICIENT", {
      insufficiency_reason: reason,
      schema_resolution: Object.assign({
        terminal_state: "INSUFFICIENT",
        selected: false,
      }, diagnostics),
    });
  };

  const required = ["classes", "courses", "learning_objects"];
  const missing = required.filter((name) => !exists(name));
  if (missing.length) {
    insufficient("REQUIRED_COLLECTION_MISSING", { missing_collection_count: missing.length });
    return;
  }

  const classDocs = d.classes.find({}).toArray();
  const courseDocs = d.courses.find({}).toArray();
  const loDocs = d.learning_objects.find({}, {
    _id: 1,
    class_id: 1, turma_id: 1, classId: 1, class: 1, class_uuid: 1,
    course_id: 1, component_id: 1, disciplina_id: 1, courseId: 1, componentId: 1,
    date: 1, data: 1, lesson_date: 1, data_aula: 1, class_date: 1,
    recorded_by: 1, created_by: 1, updated_by: 1, teacher_id: 1,
    staff_id: 1, professor_id: 1, user_id: 1, actor_id: 1,
    assignment_id: 1,
    content: 1, methodology: 1, observations: 1,
  }).toArray();

  const observed = {
    class_name_keys: safeObserved(classDocs, CLASS_NAME_KEYS),
    class_id_keys: safeObserved(classDocs, CLASS_ID_KEYS),
    class_group_keys: safeObserved(classDocs, CLASS_GROUP_KEYS),
    class_year_keys: safeObserved(classDocs, CLASS_YEAR_KEYS),
    course_name_keys: safeObserved(courseDocs, COURSE_NAME_KEYS),
    course_id_keys: safeObserved(courseDocs, COURSE_ID_KEYS),
    learning_object_class_keys: safeObserved(loDocs, LO_CLASS_KEYS),
    learning_object_course_keys: safeObserved(loDocs, LO_COURSE_KEYS),
    learning_object_date_keys: safeObserved(loDocs, LO_DATE_KEYS),
    learning_object_actor_keys: safeObserved(loDocs, ACTOR_FIELDS),
  };

  const classNameKeys = observed.class_name_keys.filter((key) => {
    const names = new Set(classDocs.map((r) => norm(get(r, key))).filter(Boolean));
    return ALL_CLASSES.every((name) => names.has(norm(name)));
  });
  if (!classNameKeys.length) {
    insufficient("CLASS_NAME_SCHEMA_NOT_RESOLVED", {
      observed_aliases: observed,
      viable_class_name_aliases: 0,
    });
    return;
  }

  const courseSchemas = [];
  for (const nameKey of observed.course_name_keys) {
    for (const idKey of observed.course_id_keys) {
      const ids = unique(courseDocs
        .filter((r) => norm(get(r, nameKey)) === norm("Matemática"))
        .map((r) => sid(get(r, idKey)))
        .filter(Boolean));
      if (ids.length) courseSchemas.push({ nameKey, idKey, mathIds: new Set(ids) });
    }
  }
  if (!courseSchemas.length) {
    insufficient("MATH_COURSE_SCHEMA_NOT_RESOLVED", {
      observed_aliases: observed,
      viable_class_name_aliases: classNameKeys.length,
      viable_course_schemas: 0,
    });
    return;
  }

  const dateKeys = observed.learning_object_date_keys.filter((key) => loDocs.some((r) => inPeriod(get(r, key))));
  if (!dateKeys.length) {
    insufficient("LEARNING_OBJECT_DATE_SCHEMA_NOT_RESOLVED", {
      observed_aliases: observed,
      viable_class_name_aliases: classNameKeys.length,
      viable_course_schemas: courseSchemas.length,
      viable_date_aliases: 0,
    });
    return;
  }

  const idRefPairs = [];
  for (const classIdKey of observed.class_id_keys) {
    const classIds = new Set(classDocs.map((r) => sid(get(r, classIdKey))).filter(Boolean));
    if (!classIds.size) continue;
    for (const loClassKey of observed.learning_object_class_keys) {
      let overlap = 0;
      for (const row of loDocs) {
        const ref = sid(get(row, loClassKey));
        if (ref && classIds.has(ref)) {
          overlap += 1;
          if (overlap >= 2) break;
        }
      }
      if (overlap > 0) idRefPairs.push({ classIdKey, loClassKey });
    }
  }
  if (!idRefPairs.length) {
    insufficient("CLASS_REFERENCE_SCHEMA_NOT_RESOLVED", {
      observed_aliases: observed,
      viable_class_name_aliases: classNameKeys.length,
      viable_course_schemas: courseSchemas.length,
      viable_date_aliases: dateKeys.length,
      viable_class_reference_pairs: 0,
    });
    return;
  }

  const yearOptions = [null, ...observed.class_year_keys];

  const mathRowsFor = (classId, loClassKey, courseSchema, loCourseKey, dateKey) =>
    loDocs.filter((row) =>
      sid(get(row, loClassKey)) === classId &&
      inPeriod(get(row, dateKey)) &&
      courseSchema.mathIds.has(sid(get(row, loCourseKey)))
    );

  const allRowsFor = (classId, loClassKey, dateKey) =>
    loDocs.filter((row) => sid(get(row, loClassKey)) === classId && inPeriod(get(row, dateKey)));

  const structuralSolutions = [];
  for (const classNameKey of classNameKeys) {
    for (const { classIdKey, loClassKey } of idRefPairs) {
      for (const groupKey of observed.class_group_keys) {
        for (const yearKey of yearOptions) {
          const relevant = classDocs.filter((r) => {
            const name = norm(get(r, classNameKey));
            if (!ALL_CLASSES.some((n) => norm(n) === name)) return false;
            if (!sid(get(r, classIdKey)) || !sid(get(r, groupKey))) return false;
            if (yearKey) {
              const y = sid(get(r, yearKey));
              if (y && y !== "2026") return false;
            }
            return true;
          });
          if (!relevant.length) continue;
          const groups = unique(relevant.map((r) => sid(get(r, groupKey))).filter(Boolean));
          for (const groupValue of groups) {
            const rows = relevant.filter((r) => sid(get(r, groupKey)) === groupValue);
            const classMap = {};
            let sixUnique = true;
            for (const name of ALL_CLASSES) {
              const matches = rows.filter((r) => norm(get(r, classNameKey)) === norm(name));
              if (matches.length !== 1) {
                sixUnique = false;
                break;
              }
              classMap[name] = sid(get(matches[0], classIdKey));
            }
            if (!sixUnique) continue;

            for (const courseSchema of courseSchemas) {
              for (const loCourseKey of observed.learning_object_course_keys) {
                const courseRefObserved = loDocs.some((r) => courseSchema.mathIds.has(sid(get(r, loCourseKey))));
                if (!courseRefObserved) continue;
                for (const dateKey of dateKeys) {
                  const controlCounts = CONTROLS.map((name) =>
                    mathRowsFor(classMap[name], loClassKey, courseSchema, loCourseKey, dateKey).length
                  );
                  if (!controlCounts.every((count) => count > 0)) continue;
                  structuralSolutions.push({
                    classNameKey,
                    classIdKey,
                    groupKey,
                    yearKey,
                    loClassKey,
                    courseNameKey: courseSchema.nameKey,
                    courseIdKey: courseSchema.idKey,
                    loCourseKey,
                    dateKey,
                    mathIds: courseSchema.mathIds,
                    classMap,
                    controlCounts,
                  });
                }
              }
            }
          }
        }
      }
    }
  }

  const solutionSignatures = new Map();
  for (const s of structuralSolutions) {
    const signature = [
      s.classNameKey, s.classIdKey, s.groupKey, s.loClassKey,
      s.courseNameKey, s.courseIdKey, s.loCourseKey, s.dateKey,
      ALL_CLASSES.map((name) => s.classMap[name]).join("|"),
    ].join("::");
    if (!solutionSignatures.has(signature)) solutionSignatures.set(signature, s);
  }
  const solutions = [...solutionSignatures.values()];

  if (solutions.length !== 1) {
    insufficient(
      solutions.length === 0 ? "NO_UNIQUE_SIX_CLASS_FOUR_CONTROL_SCHEMA_SOLUTION" : "MULTIPLE_STRUCTURAL_SCHEMA_SOLUTIONS",
      {
        observed_aliases: observed,
        viable_class_name_aliases: classNameKeys.length,
        viable_course_schemas: courseSchemas.length,
        viable_date_aliases: dateKeys.length,
        viable_class_reference_pairs: idRefPairs.length,
        structural_solution_count: solutions.length,
      }
    );
    return;
  }

  const selected = solutions[0];
  const schemaResolution = {
    terminal_state: "RESOLVED",
    selected: true,
    structural_matches: 1,
    selected_by_six_classes_and_four_math_controls: true,
    class_name_alias: selected.classNameKey,
    class_id_alias: selected.classIdKey,
    class_group_alias: selected.groupKey,
    class_year_alias: selected.yearKey,
    learning_object_class_alias: selected.loClassKey,
    course_name_alias: selected.courseNameKey,
    course_id_alias: selected.courseIdKey,
    learning_object_course_alias: selected.loCourseKey,
    learning_object_date_alias: selected.dateKey,
    controls_requiring_math_evidence: CONTROLS.length,
    required_unique_classes: ALL_CLASSES.length,
  };

  const mathRows = (name) =>
    mathRowsFor(
      selected.classMap[name],
      selected.loClassKey,
      { mathIds: selected.mathIds },
      selected.loCourseKey,
      selected.dateKey
    );

  const staffById = new Set();
  const staffIdsByUser = new Map();
  if (exists("staff")) {
    for (const r of d.staff.find({}, { _id: 0, id: 1, user_id: 1 }).toArray()) {
      const staffId = sid(r.id);
      const userId = sid(r.user_id);
      if (staffId) staffById.add(staffId);
      if (staffId && userId) {
        if (!staffIdsByUser.has(userId)) staffIdsByUser.set(userId, new Set());
        staffIdsByUser.get(userId).add(staffId);
      }
    }
  }
  const principalRaw = (v) => {
    const value = sid(v);
    if (!value) return "";
    if (staffById.has(value)) return `staff:${value}`;
    const mapped = staffIdsByUser.get(value);
    if (mapped && mapped.size === 1) return `staff:${[...mapped][0]}`;
    return `raw:${value}`;
  };
  const principals = (row) => {
    const out = new Set();
    for (const field of ACTOR_FIELDS) {
      const p = principalRaw(get(row, field));
      if (p) out.add(p);
    }
    return out;
  };

  const controls = {};
  for (const name of CONTROLS) controls[name] = mathRows(name);

  let actorPrincipal = "";
  let actorStaffId = "";
  let actorSource = "";
  let controlClassSupport = null;
  let metadataCoveragePercent = null;

  if (exists("teacher_assignments")) {
    const assignmentDocs = d.teacher_assignments.find({}).toArray();
    const observedAssign = {
      class: safeObserved(assignmentDocs, ASSIGN_CLASS_KEYS),
      course: safeObserved(assignmentDocs, ASSIGN_COURSE_KEYS),
      staff: safeObserved(assignmentDocs, ASSIGN_STAFF_KEYS),
      year: safeObserved(assignmentDocs, ASSIGN_YEAR_KEYS),
      status: safeObserved(assignmentDocs, ASSIGN_STATUS_KEYS),
    };
    const assignmentSolutions = [];
    for (const classKey of observedAssign.class) {
      for (const courseKey of observedAssign.course) {
        for (const staffKey of observedAssign.staff) {
          for (const yearKey of [null, ...observedAssign.year]) {
            const perControl = [];
            let valid = true;
            for (const name of CONTROLS) {
              const rows = assignmentDocs.filter((r) => {
                if (sid(get(r, classKey)) !== selected.classMap[name]) return false;
                if (!selected.mathIds.has(sid(get(r, courseKey)))) return false;
                if (yearKey) {
                  const y = sid(get(r, yearKey));
                  if (y && y !== "2026") return false;
                }
                for (const statusKey of observedAssign.status) {
                  if (norm(get(r, statusKey)) === "inactive") return false;
                }
                return Boolean(sid(get(r, staffKey)));
              });
              const values = unique(rows.map((r) => principalRaw(get(r, staffKey))).filter(Boolean));
              if (values.length !== 1) {
                valid = false;
                break;
              }
              perControl.push(values[0]);
            }
            if (valid && new Set(perControl).size === 1) {
              assignmentSolutions.push({ principal: perControl[0], staffKey });
            }
          }
        }
      }
    }
    const assignmentPrincipals = unique(assignmentSolutions.map((x) => x.principal));
    if (assignmentPrincipals.length === 1) {
      actorPrincipal = assignmentPrincipals[0];
      actorStaffId = actorPrincipal.startsWith("staff:") ? actorPrincipal.slice(6) : "";
      actorSource = "TEACHER_ASSIGNMENTS_ADAPTIVE_EXACT_CONTROL_UNANIMOUS";
      controlClassSupport = 4;
    }
  }

  if (!actorPrincipal) {
    const totalRows = CONTROLS.reduce((sum, name) => sum + controls[name].length, 0);
    const stats = new Map();
    for (const name of CONTROLS) {
      for (const row of controls[name]) {
        for (const p of principals(row)) {
          if (!stats.has(p)) stats.set(p, { rows: 0, classes: new Set() });
          const s = stats.get(p);
          s.rows += 1;
          s.classes.add(name);
        }
      }
    }
    const candidates = [...stats.entries()]
      .map(([principal, s]) => ({
        principal,
        rows: s.rows,
        support: s.classes.size,
        coverage: totalRows ? (100 * s.rows / totalRows) : 0,
      }))
      .filter((x) => x.support === 4 && x.coverage >= 80)
      .sort((a, b) => b.coverage - a.coverage || b.rows - a.rows || a.principal.localeCompare(b.principal));
    if (candidates.length) {
      const top = candidates[0];
      const tied = candidates.filter((x) => x.coverage === top.coverage && x.rows === top.rows);
      if (tied.length === 1) {
        actorPrincipal = top.principal;
        actorStaffId = actorPrincipal.startsWith("staff:") ? actorPrincipal.slice(6) : "";
        actorSource = "LEARNING_OBJECT_METADATA_ADAPTIVE_FOUR_CLASS_DOMINANT";
        controlClassSupport = top.support;
        metadataCoveragePercent = Math.round(top.coverage * 100) / 100;
      }
    }
  }

  if (!actorPrincipal) {
    insufficient("ACTOR_IDENTITY_NOT_UNIQUELY_DERIVABLE_FROM_AVAILABLE_HISTORICAL_FIELDS", {
      observed_aliases: observed,
      structural_solution_count: 1,
      selected_schema: schemaResolution,
      controls: CONTROLS.map((name) => ({
        class: name,
        math_rows: controls[name].length,
        math_payload_rows: controls[name].filter(payload).length,
      })),
    });
    return;
  }

  if (metadataCoveragePercent === null) {
    const totalRows = CONTROLS.reduce((sum, name) => sum + controls[name].length, 0);
    let actorRows = 0;
    let supportingClasses = 0;
    for (const name of CONTROLS) {
      const hits = controls[name].filter((row) => principals(row).has(actorPrincipal)).length;
      actorRows += hits;
      if (hits > 0) supportingClasses += 1;
    }
    metadataCoveragePercent = totalRows ? Math.round((10000 * actorRows / totalRows)) / 100 : 0;
    if (supportingClasses === 0) metadataCoveragePercent = 0;
  }

  const allRowsTarget = (name) =>
    allRowsFor(selected.classMap[name], selected.loClassKey, selected.dateKey);

  const assignmentMatchCount = (name) => {
    if (!actorStaffId || !exists("teacher_assignments")) return 0;
    const docs = d.teacher_assignments.find({}).toArray();
    let count = 0;
    for (const row of docs) {
      const classMatches = ASSIGN_CLASS_KEYS.some((k) => sid(get(row, k)) === selected.classMap[name]);
      const courseMatches = ASSIGN_COURSE_KEYS.some((k) => selected.mathIds.has(sid(get(row, k))));
      const staffMatches = ASSIGN_STAFF_KEYS.some((k) => principalRaw(get(row, k)) === actorPrincipal);
      const yearOk = ASSIGN_YEAR_KEYS.every((k) => {
        const y = sid(get(row, k));
        return !y || y === "2026";
      });
      const active = ASSIGN_STATUS_KEYS.every((k) => norm(get(row, k)) !== "inactive");
      if (classMatches && courseMatches && staffMatches && yearOk && active) count += 1;
    }
    return count;
  };

  const targetResults = [];
  for (const name of TARGETS) {
    const rows = allRowsTarget(name);
    const actorRows = rows.filter((r) => principals(r).has(actorPrincipal));
    const actorMathRows = actorRows.filter((r) => selected.mathIds.has(sid(get(r, selected.loCourseKey))));
    const actorMathPayloadRows = actorMathRows.filter(payload);
    const actorNonMathPayloadRows = actorRows.filter((r) => !selected.mathIds.has(sid(get(r, selected.loCourseKey))) && payload(r));
    const unattributedMathPayloadRows = rows.filter((r) =>
      selected.mathIds.has(sid(get(r, selected.loCourseKey))) &&
      payload(r) &&
      principals(r).size === 0
    );
    const historicalMathAssignmentMatches = assignmentMatchCount(name);

    let classification;
    if (actorMathPayloadRows.length > 0) classification = "BSON_20260818_RECOVERY_SOURCE_CONFIRMED";
    else if (actorNonMathPayloadRows.length > 0) classification = "BSON_20260818_LUIZ_ROWS_UNDER_NONMATH_COMPONENT";
    else if (actorRows.length > 0) classification = "BSON_20260818_LUIZ_ROWS_WITHOUT_PAYLOAD";
    else if (historicalMathAssignmentMatches > 0) classification = "BSON_20260818_BINDING_PRESENT_CONTENT_ABSENT";
    else if (unattributedMathPayloadRows.length > 0) classification = "BSON_20260818_UNATTRIBUTED_MATH_PAYLOAD_CANDIDATE";
    else classification = "HISTORICAL_ACTOR_ABSENT_FROM_TARGET_20260818";

    targetResults.push({
      class: name,
      classification,
      inferred_actor_rows: actorRows.length,
      inferred_actor_math_rows: actorMathRows.length,
      inferred_actor_math_payload_rows: actorMathPayloadRows.length,
      inferred_actor_nonmath_payload_rows: actorNonMathPayloadRows.length,
      historical_math_assignment_matches: historicalMathAssignmentMatches,
      unattributed_math_payload_rows: unattributedMathPayloadRows.length,
    });
  }

  let overall = "TARGETS_CLASSIFIED_FROM_20260818_DUMP";
  if (targetResults.every((r) => r.classification === "HISTORICAL_ACTOR_ABSENT_FROM_TARGET_20260818")) {
    overall = "HISTORICAL_ACTOR_ABSENT_FROM_BOTH_TARGETS_20260818";
  } else if (targetResults.some((r) => r.classification === "BSON_20260818_RECOVERY_SOURCE_CONFIRMED")) {
    overall = "BSON_20260818_RECOVERY_SOURCE_CONFIRMED";
  }

  emit("COMPLETED", overall, {
    schema_resolution: schemaResolution,
    school_resolution: {
      source: "ADAPTIVE_CLASS_RELATIONAL_SCHEMA",
      structural_matches: 1,
      selected_by_six_classes_and_four_math_controls: true,
    },
    actor_inference: {
      status: "EXACT_CONTROL_DERIVED",
      source: actorSource,
      principal_kind: actorPrincipal.startsWith("staff:") ? "staff" : "raw",
      control_class_support: controlClassSupport,
      metadata_coverage_percent: metadataCoveragePercent,
    },
    controls: CONTROLS.map((name) => ({
      class: name,
      math_rows: controls[name].length,
      math_payload_rows: controls[name].filter(payload).length,
    })),
    targets: targetResults,
    boundaries: Object.assign({}, baseBoundaries, {
      school_identity_structurally_derived: true,
      historical_schema_adaptively_resolved: true,
    }),
  });
})();