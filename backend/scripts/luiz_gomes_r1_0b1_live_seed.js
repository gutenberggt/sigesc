(() => {
  const PREFIX = "LUIZ_GOMES_R1_0B1_LIVE_SEED_JSON=";
  const DIAG_PREFIX = "LUIZ_GOMES_R1_0B1_LIVE_SEED_DIAGNOSTIC_JSON=";
  const SCHOOL = "E M E I E F Jose Pereira Barbosa";
  const ALL = ["6º ANO A", "6º ANO B", "7º ANO A", "7º ANO B", "8º ANO A", "9º ANO A"];
  let stage = "BOOT";

  const sid = (v) => v === null || v === undefined ? "" : String(v).trim();
  const norm = (v) => sid(v).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("pt-BR").replace(/\s+/g, " ").trim();
  const safeToken = (v, fallback = "UNKNOWN") => {
    const t = sid(v).replace(/[^A-Za-z0-9_.$-]/g, "_").slice(0, 64);
    return t || fallback;
  };
  const boundaries = () => ({
    production_writes: false,
    student_data_read: false,
    attendance_read: false,
    grades_read: false
  });
  const emitDiagnostic = (reason, errorName = "NONE") => print(DIAG_PREFIX + JSON.stringify({
    schema: "LUIZ_GOMES_R1_0B1_SEED_DIAGNOSTIC_V1",
    reason: safeToken(reason),
    diagnostic_stage: safeToken(stage),
    error_name: safeToken(errorName, "UNKNOWN")
  }));
  const fail = (reason, extra = {}) => {
    emitDiagnostic(reason);
    print(PREFIX + JSON.stringify(Object.assign({
      schema: "LUIZ_GOMES_R1_0B1_LIVE_SEED_V1",
      status: "INCONCLUSIVE",
      reason,
      diagnostic_stage: stage,
      boundaries: boundaries()
    }, extra)));
  };

  try {
    stage = "DB_HANDLE";
    const d = db.getSiblingDB("sigesc");

    stage = "SCHOOL_QUERY";
    const schools = d.schools.find({name: SCHOOL}, {_id:0,id:1,name:1}).limit(2).toArray();
    if (schools.length !== 1 || !sid(schools[0].id)) { fail("LIVE_SCHOOL_NOT_UNIQUE", {school_matches: schools.length}); return; }
    const schoolId = sid(schools[0].id);

    stage = "CLASS_QUERY";
    const classes = d.classes.find(
      {school_id: schoolId, name: {$in: ALL}},
      {_id:0,id:1,name:1,school_id:1,academic_year:1,course_ids:1}
    ).limit(20).toArray().filter((r) => {
      const y = sid(r.academic_year);
      return !y || y === "2026";
    });

    stage = "CLASS_MAP";
    const mapped = [];
    for (const name of ALL) {
      const hits = classes.filter((r) => norm(r.name) === norm(name) && sid(r.id));
      if (hits.length !== 1) { fail("LIVE_CLASS_NOT_UNIQUE", {class_name:name,class_matches:hits.length}); return; }
      mapped.push({name, id:sid(hits[0].id), course_ids:Array.isArray(hits[0].course_ids) ? hits[0].course_ids.map(sid).filter(Boolean) : []});
    }
    if (new Set(mapped.map((x) => x.id)).size !== ALL.length) { fail("LIVE_CLASS_IDENTITIES_NOT_DISTINCT"); return; }

    stage = "COURSE_QUERY";
    const referencedCourseIds = [...new Set(mapped.flatMap((x) => x.course_ids))];
    let mathCourses = [];
    if (referencedCourseIds.length) {
      mathCourses = d.courses.find({id: {$in: referencedCourseIds}}, {_id:0,id:1,name:1}).limit(100).toArray()
        .filter((r) => norm(r.name) === norm("Matemática") && sid(r.id));
    }
    if (!mathCourses.length) {
      mathCourses = d.courses.find({name: "Matemática"}, {_id:0,id:1,name:1}).limit(20).toArray().filter((r) => sid(r.id));
    }
    const mathIds = [...new Set(mathCourses.map((r) => sid(r.id)).filter(Boolean))];

    stage = "READY_EMIT";
    print(PREFIX + JSON.stringify({
      schema: "LUIZ_GOMES_R1_0B1_LIVE_SEED_V1",
      status: "READY",
      school_id: schoolId,
      classes: mapped.map((x) => ({name:x.name,id:x.id})),
      math_course_ids: mathIds,
      boundaries: {
        production_writes: false,
        live_collections_read: ["schools","classes","courses"],
        student_data_read: false,
        attendance_read: false,
        grades_read: false,
        technical_ids_for_internal_bridge_only: true
      }
    }));
  } catch (error) {
    const errorName = safeToken(error && error.name, "UNKNOWN");
    emitDiagnostic("LIVE_SEED_UNEXPECTED_EXCEPTION", errorName);
    print(PREFIX + JSON.stringify({
      schema: "LUIZ_GOMES_R1_0B1_LIVE_SEED_V1",
      status: "INCONCLUSIVE",
      reason: "LIVE_SEED_UNEXPECTED_EXCEPTION",
      diagnostic_stage: stage,
      error_name: errorName,
      boundaries: boundaries()
    }));
  }
})();
