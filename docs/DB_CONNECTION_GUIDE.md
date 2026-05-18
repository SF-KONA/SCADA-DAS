# 🔌 DB 연결 설정 가이드

> DAS 서버(완택 노트북)의 MySQL에 연결하는 방법입니다.
> 본인 로컬 DB로 돌아가고 싶으면 원래 값으로 되돌리면 됩니다.

---

## 접속 정보

| 항목 | 값 |
|---|---|
| Host | `192.168.200.173` |
| Port | `3306` |
| Database | `scada` |
| Username | `scada_user` |
| Password | `Scada1234!` |

> ⚠️ IP는 Wi-Fi 바뀌면 변경될 수 있습니다. 안 되면 완택한테 문의

---

## 방법 1 — IntelliJ 에서 설정 (추천 ⭐)

### Step 1. 실행 설정 열기

```
상단 메뉴 → Run → Edit Configurations...
```

### Step 2. Spring Boot 설정 선택

왼쪽에서 `DemoApplication` (또는 본인 메인 클래스) 클릭

### Step 3. Environment variables 입력

`Environment variables` 항목 오른쪽 아이콘 클릭 후:

```
DB_HOST=192.168.200.173
DB_USER=scada_user
DB_PASSWORD=Scada1234!
```

한 줄에 하나씩 입력, 또는 세미콜론(;)으로 구분:

```
DB_HOST=192.168.200.173;DB_USER=scada_user;DB_PASSWORD=Scada1234!
```

### Step 4. OK → Apply → Run

끝!

---

## 방법 2 — 터미널에서 실행

### Windows (PowerShell)

```powershell
$env:DB_HOST="192.168.200.173"
$env:DB_USER="scada_user"
$env:DB_PASSWORD="Scada1234!"
./gradlew bootRun
```

### Windows (CMD)

```cmd
set DB_HOST=192.168.200.173
set DB_USER=scada_user
set DB_PASSWORD=Scada1234!
gradlew bootRun
```

### Mac / Linux

```bash
DB_HOST=192.168.200.173 DB_USER=scada_user DB_PASSWORD=Scada1234! ./gradlew bootRun
```

---

## 로컬 DB로 돌아가기

IntelliJ Environment variables를 원래 값으로 변경:

```
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=본인비밀번호
```

---

## application.properties 변경 (1회만)

`localhost` → `${DB_HOST:localhost}` 로 변경 필요:

```properties
# 변경 전
spring.datasource.url=jdbc:mysql://localhost:3306/scada?serverTimezone=Asia/Seoul

# 변경 후
spring.datasource.url=jdbc:mysql://${DB_HOST:localhost}:3306/scada?serverTimezone=Asia/Seoul
```

> 이렇게 하면 DB_HOST 환경변수가 없을 때는 기존처럼 localhost로 동작합니다.
> 기존 개발 환경에 영향 없습니다.
