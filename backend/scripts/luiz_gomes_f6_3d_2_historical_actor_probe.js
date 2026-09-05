(() => {
  const d = db.getSiblingDB("sigesc");
  const PREFIX = "LUIZ_GOMES_F6_3C_POINT_JSON=";
  const SCHOOL = "E M E I E F Jose Pereira Barbosa";
  const CONTROLS = ["6º ANO A", "6º ANO B", "7º ANO A", "7º ANO B"];
  const TARGETS = ["8º ANO A", "9º ANO A"];
  const ALL_CLASSES = [...CONTROLS, ...TARGETS];
  const START = "2026-02-01";
  const END = "2026-05-01";
  const ACTOR_FIELDS = ["recorded_by", "created_by", "updated_by", "teacher_id", "staff_id"];

  const sid = (v) => (v === null || v === undefined ? "" : String(v).trim());
  const norm = (v) => sid(v)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR")
    .replace(/º/g, "o")
    .replace(/ª/g, "a")
    .replace(/\s+/g, " ")
    .trim();
  const exists = (name) => d.getCollectionNames().includes(name);
  const cid = (r) => sid(r.course_id || r.component_id);
  const payload = (r) => Boolean(sid(r.content) || sid(r.methodology) || sid(r.observations));
  const emit = (status, classification, extra = {}) => print(PREFIX + JSON.stringify(Object.assign({
    schema: "LUIZ_GOMES_F6_3D_2_HISTORICAL_ACTOR_V2",
    status,
    overall_classification: classification,
    source_date: "2026-08-18",
    school: SCHOOL,
    period: { from: START, to_exclusive: END },
    boundaries: {
      actor_identity_derived_without_user_lookup: true,
      technical_ids_emitted: false,
      pedagogical_plaintext_emitted: false,
      pedagogical_payload_boolean_only: true,
      attendance_records_read: false,
      student_data_read: false,
      production_writes: false,
      school_identity_structurally_derived: false,
    },
  }, extra)));

  const required = ["schools", "classes", "courses", "learning_objects"];
  const missing = required.filter((name) => !exists(name));
  if (missing.length) {
    emit("INCONCLUSIVE", "REQUIRED_COLLECTION_MISSING", { context: { missing_count: missing.length } });
    return;
  }

  const courses = d.courses.find({}, { _id: 0, id: 1, name: 1 }).toArray();
  const mathIds = new Set(courses.filter((r) => norm(r.name) === norm("Matemática")).map((r) => sid(r.id)).filter(Boolean));
  if (!mathIds.size) {
    emit("INCONCLUSIVE", "MATH_COURSE_IDENTITY_NOT_FOUND", { context: { math_identity_count: 0 } });
    return;
  }

  const loadRows = (classId, mathOnly) => {
    const q = { class_id: classId, date: { $gte: START, $lt: END } };
    if (mathOnly) q.$or = [
      { course_id: { $in: [...mathIds] } },
      { component_id: { $in: [...mathIds] } },
    ];
    return d.learning_objects.find(q, {
      _id: 0,
      date: 1,
      course_id: 1,
      component_id: 1,
      recorded_by: 1,
      created_by: 1,
      updated_by: 1,
      teacher_id: 1,
      staff_id: 1,
      assignment_id: 1,
      content: 1,
      methodology: 1,
      observations: 1,
    }).toArray();
  };

  const schoolNameCandidates = d.schools.find({}, { _id: 0, id: 1, name: 1 }).toArray()
    .filter((r) => norm(r.name) === norm(SCHOOL) && sid(r.id));
  if (!schoolNameCandidates.length) {
    emit("INCONCLUSIVE", "SCHOOL_CONTEXT_NOT_FOUND", { school_resolution: { name_matches: 0, structural_matches: 0 } });
    return;
  }

  const allClasses = d.classes.find({}, { _id: 0, id: 1, school_id: 1, name: 1, academic_year: 1 }).toArray();
  const qualifiedSchools = [];
  for (const school of schoolNameCandidates) {
    const schoolId = sid(school.id);
    const classes = allClasses.filter((r) => sid(r.school_id) === schoolId && (!sid(r.academic_year) || sid(r.academic_year) === "2026"));
    const classMap = {};
    let sixUnique = true;
    for (const name of ALL_CLASSES) {
      const matches = classes.filter((r) => norm(r.name) === norm(name) && sid(r.id));
      if (matches.length !== 1) {
        sixUnique = false;
        break;
      }
      classMap[name] = sid(matches[0].id);
    }
    if (!sixUnique) continue;
    const controlEvidence = CONTROLS.map((name) => loadRows(classMap[name], true).length);
    if (controlEvidence.every((count) => count > 0)) {
      qualifiedSchools.push({ schoolId, classMap, controlEvidence });
    }
  }

  if (qualifiedSchools.length !== 1) {
    emit("INCONCLUSIVE", qualifiedSchools.length === 0 ? "SCHOOL_CONTEXT_NOT_STRUCTURALLY_RESOLVED" : "SCHOOL_CONTEXT_STRUCTURAL_AMBIGUITY", {
      school_resolution: {
        name_matches: schoolNameCandidates.length,
        structural_matches: qualifiedSchools.length,
        required_unique_classes: ALL_CLASSES.length,
        controls_requiring_math_evidence: CONTROLS.length,
      },
    });
    return;
  }

  const selected = qualifiedSchools[0];
  const classByName = selected.classMap;

  const staffById = new Map();
  const staffIdsByUser = new Map();
  if (exists("staff")) {
    for (const r of d.staff.find({}, { _id: 0, id: 1, user_id: 1 }).toArray()) {
      const s = sid(r.id); const u = sid(r.user_id);
      if (s) staffById.set(s, true);
      if (s && u) {
        if (!staffIdsByUser.has(u)) staffIdsByUser.set(u, new Set());
        staffIdsByUser.get(u).add(s);
      }
    }
  }

  const principalRaw = (v) => {
    const x = sid(v);
    if (!x) return "";
    if (staffById.has(x)) return `staff:${x}`;
    const ss = staffIdsByUser.get(x);
    if (ss && ss.size === 1) return `staff:${[...ss][0]}`;
    return `raw:${x}`;
  };
  const principals = (r) => {
    const out = new Set();
    for (const field of ACTOR_FIELDS) {
      const p = principalRaw(r[field]);
      if (p) out.add(p);
    }
    return out;
  };

  const assignments = exists("teacher_assignments")
    ? d.teacher_assignments.find({}, { _id: 0, id: 1, staff_id: 1, class_id: 1, course_id: 1, component_id: 1, academic_year: 1, status: 1 }).toArray()
    : [];
  const assignmentStaff = (classId) => new Set(assignments.filter((r) =>
    sid(r.class_id) === classId &&
    mathIds.has(cid(r)) &&
    (!sid(r.academic_year) || sid(r.academic_year) === "2026") &&
    norm(r.status) !== "inactive" &&
    sid(r.staff_id)
  ).map((r) => sid(r.staff_id)));

  const controlRows = {};
  const controlAssignmentSets = {};
  for (const name of CONTROLS) {
    controlRows[name] = loadRows(classByName[name], true);
    controlAssignmentSets[name] = assignmentStaff(classByName[name]);
  }

  let actorPrincipal = "";
  let actorStaffId = "";
  let actorSource = "";
  let actorKind = "";
  let controlClassSupport = null;
  let metadataCoveragePercent = null;

  const exactAssignmentIds = CONTROLS.map((name) => [...controlAssignmentSets[name]]);
  if (exactAssignmentIds.every((ids) => ids.length === 1) && new Set(exactAssignmentIds.map((ids) => ids[0])).size === 1) {
    actorStaffId = exactAssignmentIds[0][0];
    actorPrincipal = `staff:${actorStaffId}`;
    actorSource = "TEACHER_ASSIGNMENTS_EXACT_CONTROL_UNANIMOUS";
    actorKind = "staff";
    controlClassSupport = 4;
  } else {
    const totalRows = CONTROLS.reduce((sum, name) => sum + controlRows[name].length, 0);
    const stats = new Map();
    for (const name of CONTROLS) {
      for (const row of controlRows[name]) {
        for (const p of principals(row)) {
          if (!stats.has(p)) stats.set(p, { rows: 0, classes: new Set() });
          const s = stats.get(p); s.rows += 1; s.classes.add(name);
        }
      }
    }
    const candidates = [...stats.entries()].map(([principal, s]) => ({
      principal,
      rows: s.rows,
      support: s.classes.size,
      coverage: totalRows ? (100 * s.rows / totalRows) : 0,
    })).filter((x) => x.support === 4 && x.coverage >= 80)
      .sort((a, b) => b.coverage - a.coverage || b.rows - a.rows || a.principal.localeCompare(b.principal));
    if (candidates.length) {
      const top = candidates[0];
      const tied = candidates.filter((x) => x.coverage === top.coverage && x.rows === top.rows);
      if (tied.length === 1) {
        actorPrincipal = top.principal;
        actorSource = "LEARNING_OBJECT_METADATA_FOUR_CLASS_DOMINANT";
        actorKind = actorPrincipal.startsWith("staff:") ? "staff" : "raw";
        actorStaffId = actorPrincipal.startsWith("staff:") ? actorPrincipal.slice(6) : "";
        controlClassSupport = top.support;
        metadataCoveragePercent = Math.round(top.coverage * 100) / 100;
      }
    }
  }

  if (!actorPrincipal) {
    emit("INCONCLUSIVE", "HISTORICAL_ACTOR_NOT_UNIQUELY_INFERRED", {
      school_resolution: {
        name_matches: schoolNameCandidates.length,
        structural_matches: 1,
        selected_by_six_classes_and_four_math_controls: true,
      },
      actor_inference: {
        status: "NOT_DERIVED",
        source: null,
        principal_kind: null,
        control_class_support: null,
        metadata_coverage_percent: null,
      },
      controls: CONTROLS.map((name) => ({
        class: name,
        math_rows: controlRows[name].length,
        math_payload_rows: controlRows[name].filter(payload).length,
        assignment_staff_candidates: controlAssignmentSets[name].size,
      })),
      boundaries: {
        actor_identity_derived_without_user_lookup: true,
        technical_ids_emitted: false,
        pedagogical_plaintext_emitted: false,
        pedagogical_payload_boolean_only: true,
        attendance_records_read: false,
        student_data_read: false,
        production_writes: false,
        school_identity_structurally_derived: true,
      },
    });
    return;
  }

  if (actorSource === "TEACHER_ASSIGNMENTS_EXACT_CONTROL_UNANIMOUS") {
    const totalRows = CONTROLS.reduce((sum, name) => sum + controlRows[name].length, 0);
    let actorRows = 0;
    let supportingClasses = 0;
    for (const name of CONTROLS) {
      let classRows = 0;
      for (const row of controlRows[name]) {
        if (principals(row).has(actorPrincipal)) { actorRows += 1; classRows += 1; }
      }
      if (classRows > 0) supportingClasses += 1;
    }
    metadataCoveragePercent = totalRows ? Math.round((10000 * actorRows / totalRows)) / 100 : 0;
    if (totalRows > 0 && supportingClasses > 0 && metadataCoveragePercent < 20) {
      emit("INCONCLUSIVE", "ACTOR_ASSIGNMENT_METADATA_CONFLICT", {
        school_resolution: { name_matches: schoolNameCandidates.length, structural_matches: 1, selected_by_six_classes_and_four_math_controls: true },
        actor_inference: { status: "CONFLICT", source: actorSource, principal_kind: actorKind, control_class_support: controlClassSupport, metadata_coverage_percent: metadataCoveragePercent },
      });
      return;
    }
  }

  const targetResults = [];
  for (const name of TARGETS) {
    const allRows = loadRows(classByName[name], false);
    const actorRows = allRows.filter((r) => principals(r).has(actorPrincipal));
    const actorMathRows = actorRows.filter((r) => mathIds.has(cid(r)));
    const actorMathPayloadRows = actorMathRows.filter(payload);
    const actorNonMathPayloadRows = actorRows.filter((r) => !mathIds.has(cid(r)) && payload(r));
    const unattributedMathPayloadRows = allRows.filter((r) => mathIds.has(cid(r)) && payload(r) && principals(r).size === 0);
    let historicalMathAssignmentMatches = 0;
    if (actorStaffId) {
      historicalMathAssignmentMatches = assignments.filter((r) =>
        sid(r.class_id) === classByName[name] &&
        mathIds.has(cid(r)) &&
        (!sid(r.academic_year) || sid(r.academic_year) === "2026") &&
        norm(r.status) !== "inactive" &&
        sid(r.staff_id) === actorStaffId
      ).length;
    }

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
      inferred_actor_math_payload_rows: actorMathPayloadRows.length,
      inferred_actor_nonmath_payload_rows: actorNonMathPayloadRows.length,
      historical_math_assignment_matches: historicalMathAssignmentMatches,
      unattributed_math_payload_rows: unattributedMathPayloadRows.length,
    });
  }

  const targetClasses = targetResults.map((r) => r.classification);
  let overall;
  if (targetClasses.includes("BSON_20260818_RECOVERY_SOURCE_CONFIRMED")) overall = "BSON_20260818_RECOVERY_SOURCE_CONFIRMED";
  else if (targetClasses.includes("BSON_20260818_LUIZ_ROWS_UNDER_NONMATH_COMPONENT")) overall = "BSON_20260818_LUIZ_ROWS_UNDER_NONMATH_COMPONENT";
  else if (targetClasses.includes("BSON_20260818_BINDING_PRESENT_CONTENT_ABSENT")) overall = "BSON_20260818_BINDING_PRESENT_CONTENT_ABSENT";
  else if (targetClasses.includes("BSON_20260818_LUIZ_ROWS_WITHOUT_PAYLOAD")) overall = "BSON_20260818_LUIZ_ROWS_WITHOUT_PAYLOAD";
  else if (targetClasses.includes("BSON_20260818_UNATTRIBUTED_MATH_PAYLOAD_CANDIDATE")) overall = "BSON_20260818_UNATTRIBUTED_MATH_PAYLOAD_CANDIDATE";
  else overall = "HISTORICAL_ACTOR_ABSENT_FROM_BOTH_TARGETS_20260818";

  emit("COMPLETED", overall, {
    school_resolution: {
      name_matches: schoolNameCandidates.length,
      structural_matches: 1,
      selected_by_six_classes_and_four_math_controls: true,
    },
    actor_inference: {
      status: "EXACT_CONTROL_DERIVED",
      source: actorSource,
      principal_kind: actorKind,
      control_class_support: controlClassSupport,
      metadata_coverage_percent: metadataCoveragePercent,
    },
    controls: CONTROLS.map((name) => ({
      class: name,
      math_rows: controlRows[name].length,
      math_payload_rows: controlRows[name].filter(payload).length,
      assignment_staff_candidates: controlAssignmentSets[name].size,
    })),
    targets: targetResults,
    boundaries: {
      actor_identity_derived_without_user_lookup: true,
      technical_ids_emitted: false,
      pedagogical_plaintext_emitted: false,
      pedagogical_payload_boolean_only: true,
      attendance_records_read: false,
      student_data_read: false,
      production_writes: false,
      school_identity_structurally_derived: true,
    },
  });
})();
