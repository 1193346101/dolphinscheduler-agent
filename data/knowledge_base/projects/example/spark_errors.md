# Spark Error Knowledge Base

Example knowledge base for Spark task errors.

## OOM Errors

### Executor OOM (Java Heap Space)

**Pattern:** `java.lang.OutOfMemoryError: Java heap space`

**Cause:** Executor memory insufficient for data processing

**Solution:**
```yaml
config_changes:
  spark.executor.memory: "4g"
  spark.executor.memoryOverhead: "1g"
```

**Risk Level:** LOW

---

### Driver OOM (Native Thread)

**Pattern:** `OutOfMemoryError: unable to create new native thread`

**Cause:** Driver memory insufficient, too many concurrent tasks

**Solution:**
```yaml
config_changes:
  spark.driver.memory: "2g"
  spark.driver.maxResultSize: "2g"
```

**Risk Level:** LOW

---

### Container Killed (Memory)

**Pattern:** `Container killed due to memory`

**Cause:** Container exceeded YARN memory limits

**Solution:**
```yaml
config_changes:
  spark.executor.memory: "4g"
  spark.executor.memoryOverhead: "1g"
  spark.driver.memory: "2g"
```

**Risk Level:** LOW

---

## Timeout Errors

### Broadcast Timeout

**Pattern:** `BroadcastHashJoin.*timeout|broadcast.*timeout`

**Cause:** Broadcast join data too large, timeout during broadcast

**Solution:**
```yaml
config_changes:
  spark.sql.autoBroadcastJoinThreshold: "-1"
```

**Alternative:** Increase broadcast timeout
```yaml
config_changes:
  spark.sql.broadcastTimeout: "600"
```

**Risk Level:** LOW

---

### Shuffle Timeout

**Pattern:** `shuffle.*timeout`

**Cause:** Shuffle data transfer timeout

**Solution:**
```yaml
config_changes:
  spark.shuffle.io.timeout: "120s"
  spark.network.timeout: "300s"
```

**Risk Level:** LOW

---

### Network Timeout

**Pattern:** `spark.network.timeout`

**Cause:** Network communication timeout

**Solution:**
```yaml
config_changes:
  spark.network.timeout: "300s"
  spark.rpc.timeout: "300s"
```

**Risk Level:** LOW

---

## Class/Dependency Errors

### ClassNotFoundException

**Pattern:** `ClassNotFoundException`

**Cause:** Missing class in classpath

**Analysis Required:** Check the missing class name and required JAR

**LLM Hint:** Spark class not found, analyze the missing class name and required dependencies

**Risk Level:** MEDIUM

---

### NoClassDefFoundError

**Pattern:** `NoClassDefFoundError`

**Cause:** Class definition not found at runtime

**Analysis Required:** Check class name and dependency loading issues

**LLM Hint:** Spark class definition not found, analyze class name and dependency loading

**Risk Level:** MEDIUM

---

## Data Errors

### HDFS File Not Found

**Pattern:** `does not exist|FileNotFound|InvalidInputException.*path`

**Cause:** Input file or path does not exist

**Analysis Required:** Check if the input path is correct

**LLM Hint:** HDFS file not found, check if input path is correct

**Risk Level:** MEDIUM

---

### Schema Mismatch

**Pattern:** `Schema mismatch|cannot resolve`

**Cause:** Data schema does not match expected schema

**Analysis Required:** Check data structure and schema definition

**LLM Hint:** Schema mismatch, analyze data structure issues

**Risk Level:** MEDIUM

---

## Resource Errors

### GC Overhead Limit Exceeded

**Pattern:** `GC overhead limit exceeded`

**Cause:** Too much time spent on garbage collection

**Solution:**
```yaml
config_changes:
  spark.executor.memory: "8g"
  spark.executor.memoryOverhead: "2g"
  spark.driver.memory: "4g"
```

**Risk Level:** LOW

---

### Executor Heartbeat Timeout

**Pattern:** `Executor heartbeat timeout`

**Cause:** Executor lost connection with driver

**Solution:**
```yaml
config_changes:
  spark.executor.heartbeatInterval: "60s"
  spark.network.timeout: "300s"
```

**Risk Level:** LOW