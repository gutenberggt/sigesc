(() => {
  const d = db.getSiblingDB("sigesc");
  const PREFIX = "LUIZ_GOMES_R1_0B1_RESULT_JSON=";
  const CONTROLS = ["6º ANO A", "6º ANO B", "7º ANO A", "7º ANO B"];
  const TARGETS = ["8º ANO A", "9º ANO A"];
  const ALL = [...CONTROLS, ...TARGETS];
  const START = "2026-02-01";
  const END = "2026-05-01";
  const SKIP_KEYS = new Set(["content","methodology","observations","resources","records","students","student","grades","notes","password","token"]);
  const sid = (v) => {
    if (v === null || v === undefined) return "";
    if (typeof v === "object" && typeof v.valueOf === "function") {
      try { const x=v.valueOf(); if (x !== v && x !== null && x !== undefined) return String(x).trim(); } catch (_) {}
    }
    return String(v).trim();
  };
  const norm = (v) => sid(v).normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLocaleLowerCase("pt-BR").replace(/\s+/g," ").trim();
  const scalar = (v) => v === null || v === undefined || ["string","number","boolean"].includes(typeof v) || (typeof v === "object" && typeof v.valueOf === "function" && v.valueOf() !== v);
  const leaves = (obj, prefix="", depth=0, out=[]) => {
    if (!obj || typeof obj !== "object" || depth > 4) return out;
    for (const [key,value] of Object.entries(obj)) {
      if (SKIP_KEYS.has(String(key).toLocaleLowerCase("pt-BR"))) continue;
      const path = prefix ? `${prefix}.${key}` : key;
      if (Array.isArray(value)) {
        for (const item of value.slice(0,32)) scalar(item) ? out.push([`${path}[]`,sid(item)]) : leaves(item,`${path}[]`,depth+1,out);
      } else if (scalar(value)) out.push([path,sid(value)]);
      else leaves(value,path,depth+1,out);
    }
    return out;
  };
  const byPath = (doc) => { const m=new Map(); for (const [p,v] of leaves(doc)) { if(!m.has(p))m.set(p,[]); m.get(p).push(v); } return m; };
  const valuesAt = (doc,path) => byPath(doc).get(path) || [];
  const uniq = (xs) => [...new Set(xs)];
  const inPeriod = (v) => { const s=sid(v).slice(0,10); return /^\d{4}-\d{2}-\d{2}$/.test(s) && s>=START && s<END; };
  const payloadPresent = (row) => ["content","methodology","observations","resources"].some((k) => {
    const v=row && row[k]; if(Array.isArray(v))return v.length>0; if(v && typeof v==="object")return Object.keys(v).length>0; return sid(v)!=="";
  });
  const boundaries = {
    production_writes:false, live_metadata_reads:true, source_dump_read_only:true, temporary_mongo_network_none:true,
    student_data_read:false, attendance_records_read:false, grades_read:false, pedagogical_plaintext_emitted:false,
    technical_ids_emitted:false, actor_attribution_attempted:false, ephemeral_technical_identity_cleanup_required:true,
    fail_closed_on_ambiguity:true
  };
  const emit = (status, classification, extra={}) => print(PREFIX+JSON.stringify(Object.assign({
    schema:"LUIZ_GOMES_R1_0B1_TEMPORAL_IDENTITY_V1",status,overall_classification:classification,
    source_date:"2026-08-18",period:{from:START,to_exclusive:END},boundaries
  },extra)));
  const inconclusive = (reason, extra={}) => emit("INCONCLUSIVE","TEMPORAL_IDENTITY_BRIDGE_INCONCLUSIVE",Object.assign({insufficiency_reason:reason},extra));

  if (typeof LIVE_SEED === "undefined" || !LIVE_SEED || LIVE_SEED.schema !== "LUIZ_GOMES_R1_0B1_LIVE_SEED_V1" || LIVE_SEED.status !== "READY") {
    inconclusive("LIVE_SEED_INVALID"); return;
  }
  const seedClasses = Array.isArray(LIVE_SEED.classes) ? LIVE_SEED.classes : [];
  if (seedClasses.length !== 6 || !ALL.every((name) => seedClasses.some((x) => x.name===name && sid(x.id)))) {
    inconclusive("LIVE_SEED_SIX_CLASSES_REQUIRED"); return;
  }
  const names = d.getCollectionNames();
  for (const c of ["classes","courses","learning_objects"]) if (!names.includes(c)) { inconclusive("REQUIRED_COLLECTION_MISSING",{missing_collection:c}); return; }
  const classDocs=d.classes.find({}).toArray();
  const courseDocs=d.courses.find({}).toArray();
  const loDocs=d.learning_objects.find({}).toArray();
  const classPaths=uniq(classDocs.flatMap((r)=>leaves(r).map(([p])=>p)));
  const loPaths=uniq(loDocs.flatMap((r)=>leaves(r).map(([p])=>p)));
  const coursePaths=uniq(courseDocs.flatMap((r)=>leaves(r).map(([p])=>p)));

  const mapped={};
  const perClassPaths={};
  for (const seed of seedClasses) {
    const hits=classDocs.filter((doc)=>leaves(doc).some(([,v])=>v===sid(seed.id)));
    if (hits.length !== 1) continue;
    mapped[seed.name]=hits[0];
    perClassPaths[seed.name]=uniq(leaves(hits[0]).filter(([,v])=>v===sid(seed.id)).map(([p])=>p));
  }
  const preservedNames=ALL.filter((n)=>mapped[n]);
  if (preservedNames.length !== 6) {
    emit("COMPLETED","TEMPORAL_IDENTITY_NOT_PRESERVED",{
      temporal_identity_bridge:{selected:false,preserved_class_count:preservedNames.length,required_class_count:6},
      next_gate_r1_0c_open:false
    });
    return;
  }
  if (new Set(ALL.map((n)=>mapped[n])).size !== 6) { inconclusive("TEMPORAL_IDENTITIES_COLLIDE"); return; }
  let commonIdPaths=[...perClassPaths[ALL[0]]];
  for (const name of ALL.slice(1)) commonIdPaths=commonIdPaths.filter((p)=>perClassPaths[name].includes(p));
  if (!commonIdPaths.length) { inconclusive("HISTORICAL_COMMON_CLASS_ID_PATH_NOT_RESOLVED"); return; }

  const seedIdByName=Object.fromEntries(seedClasses.map((x)=>[x.name,sid(x.id)]));
  const classRefPaths=loPaths.filter((path)=>CONTROLS.every((name)=>loDocs.some((r)=>valuesAt(r,path).includes(seedIdByName[name]))));
  if (!classRefPaths.length) { inconclusive("LEARNING_OBJECT_CLASS_REFERENCE_NOT_RESOLVED",{historical_class_identity_path_candidates:commonIdPaths.length}); return; }

  const mathCandidates=[];
  const liveMathIds=new Set((LIVE_SEED.math_course_ids||[]).map(sid).filter(Boolean));
  if (liveMathIds.size) {
    for (const loCoursePath of loPaths) {
      if (loDocs.some((r)=>valuesAt(r,loCoursePath).some((v)=>liveMathIds.has(v)))) {
        mathCandidates.push({mode:"LIVE_IDENTITY_PRESERVED",loCoursePath,mathSet:new Set(liveMathIds),courseNamePath:null,courseIdPath:null});
      }
    }
  }
  if (!mathCandidates.length) {
    for (const namePath of coursePaths) {
      const mathDocs=courseDocs.filter((r)=>valuesAt(r,namePath).some((v)=>norm(v)===norm("Matemática")));
      if (!mathDocs.length) continue;
      for (const idPath of coursePaths) {
        const ids=uniq(mathDocs.flatMap((r)=>valuesAt(r,idPath)).filter(Boolean));
        if (!ids.length) continue;
        const set=new Set(ids);
        for (const loCoursePath of loPaths) if (loDocs.some((r)=>valuesAt(r,loCoursePath).some((v)=>set.has(v)))) {
          mathCandidates.push({mode:"HISTORICAL_NAME_RELATION",loCoursePath,mathSet:set,courseNamePath:namePath,courseIdPath:idPath});
        }
      }
    }
  }
  if (!mathCandidates.length) { inconclusive("MATH_REFERENCE_NOT_RESOLVED"); return; }
  const datePaths=loPaths.filter((p)=>loDocs.some((r)=>valuesAt(r,p).some(inPeriod)));
  if (!datePaths.length) { inconclusive("LEARNING_OBJECT_DATE_NOT_RESOLVED"); return; }

  const raw=[];
  for (const classIdPath of commonIdPaths) for (const loClassPath of classRefPaths) for (const math of mathCandidates) for (const datePath of datePaths) {
    const counts={}; let controlsOk=true;
    for (const name of ALL) {
      const rows=loDocs.filter((r)=>valuesAt(r,loClassPath).includes(seedIdByName[name]) && valuesAt(r,math.loCoursePath).some((v)=>math.mathSet.has(v)) && valuesAt(r,datePath).some(inPeriod));
      counts[name]=rows.length;
      if(CONTROLS.includes(name) && rows.length===0)controlsOk=false;
    }
    if(controlsOk)raw.push({classIdPath,loClassPath,math,datePath,counts});
  }
  const dedup=new Map();
  for(const s of raw){
    const sig=[s.loClassPath,[...s.math.mathSet].sort().join("|"),s.math.loCoursePath,s.datePath,ALL.map((n)=>s.counts[n]).join("|")].join("::");
    if(!dedup.has(sig))dedup.set(sig,s);
  }
  const sols=[...dedup.values()];
  if(sols.length!==1){inconclusive(sols.length?"MULTIPLE_TEMPORAL_RELATIONAL_SOLUTIONS":"NO_TEMPORAL_RELATIONAL_SOLUTION",{raw_solution_count:raw.length,deduplicated_solution_count:sols.length});return;}
  const s=sols[0];
  const summaries=[];
  for(const name of ALL){
    const rows=loDocs.filter((r)=>valuesAt(r,s.loClassPath).includes(seedIdByName[name]) && valuesAt(r,s.math.loCoursePath).some((v)=>s.math.mathSet.has(v)) && valuesAt(r,s.datePath).some(inPeriod));
    summaries.push({class_name:name,role:CONTROLS.includes(name)?"CONTROL":"TARGET",math_rows_in_period:rows.length,rows_with_payload:rows.filter(payloadPresent).length,distinct_dates:uniq(rows.flatMap((r)=>valuesAt(r,s.datePath).filter(inPeriod).map((v)=>sid(v).slice(0,10)))).length});
  }
  const targetRows=summaries.filter((x)=>x.role==="TARGET").reduce((a,x)=>a+x.math_rows_in_period,0);
  const targetPayload=summaries.filter((x)=>x.role==="TARGET").reduce((a,x)=>a+x.rows_with_payload,0);
  const classification=targetRows===0?"TEMPORAL_IDENTITY_BRIDGE_RESOLVED_NO_TARGET_MATH_ROWS":(targetPayload>0?"TEMPORAL_IDENTITY_BRIDGE_RESOLVED_TARGET_PAYLOAD_PRESENT":"TEMPORAL_IDENTITY_BRIDGE_RESOLVED_TARGET_ROWS_WITHOUT_PAYLOAD");
  emit("COMPLETED",classification,{
    temporal_identity_bridge:{selected:true,preserved_class_count:6,required_class_count:6,historical_class_identity_path:s.classIdPath,learning_object_class_ref_path:s.loClassPath,math_resolution_mode:s.math.mode,learning_object_course_ref_path:s.math.loCoursePath,learning_object_date_path:s.datePath,deduplicated_solution_count:1,control_requirement:"FOUR_CONTROLS_WITH_MATH_IN_PERIOD"},
    classes:summaries,targets_total_math_rows:targetRows,targets_total_rows_with_payload:targetPayload,next_gate_r1_0c_open:targetRows>0
  });
})();
