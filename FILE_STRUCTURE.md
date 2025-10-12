# JolChobi File Structure

## 📁 Main Application Files

### Current Structure (v2.0)

```
JolChobi/
├── app.py                    # ⭐ MAIN APP - Enhanced version (v2.0)
├── appv1.py                  # Original hackathon MVP (v1.0)
│
├── Core Modules (v2.0)
├── io_sources.py             # Data ingestion & API calls
├── model.py                  # Flood modeling
├── exposure.py               # Impact analytics
├── forecast.py               # Forecast processing
└── render.py                 # Visualization
```

## 🚀 How to Run

### Enhanced Version (Recommended)
```bash
streamlit run app.py
```
This runs the **v2.0 enhanced version** with all improvements:
- Modular architecture
- Caching & retry logic
- DEM upload
- Basemap selector
- In-memory downloads
- COG export
- Full test coverage

### Original Version (v1.0)
```bash
streamlit run appv1.py
```
This runs the **original hackathon MVP** for reference or comparison.

## 📝 File Naming Explanation

### Why `app.py` is the Enhanced Version

**Streamlit Cloud Requirement**: Streamlit Cloud and most deployment platforms expect the main application file to be named `app.py` by default.

**What Changed**:
1. ✅ `app.py` (original) → renamed to → `appv1.py`
2. ✅ `app_improved.py` (enhanced) → renamed to → `app.py`

**Result**: 
- `app.py` = Enhanced v2.0 (production-ready)
- `appv1.py` = Original v1.0 (preserved for reference)

## 🎯 Deployment

### Streamlit Cloud
When you deploy to Streamlit Cloud, it will automatically run `app.py` (the enhanced version).

### Local Development
```bash
# Default (enhanced)
streamlit run app.py

# Or specify port
streamlit run app.py --server.port=8501

# Compare with original
streamlit run appv1.py --server.port=8502
```

### Docker
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["streamlit", "run", "app.py", "--server.port=8501"]
```

## 📊 File Comparison

| Feature | app.py (v2.0) | appv1.py (v1.0) |
|---------|---------------|-----------------|
| **Architecture** | Modular (6 files) | Monolithic (1 file) |
| **Lines of Code** | ~500 (main) + modules | 1,026 (all in one) |
| **Caching** | ✅ Multi-level | ❌ None |
| **Retry Logic** | ✅ Exponential backoff | ❌ None |
| **DEM Upload** | ✅ Yes | ❌ File path only |
| **Basemaps** | ✅ 5 options | ❌ 1 (OSM) |
| **Opacity** | ✅ Sliders | ❌ Hardcoded |
| **Downloads** | ✅ In-memory | ❌ Disk only |
| **COG Export** | ✅ Yes | ❌ No |
| **Tests** | ✅ 37 tests | ❌ None |
| **Type Hints** | ✅ Full | ⚠️ Partial |
| **Documentation** | ✅ 9 guides | ⚠️ 1 README |

## 🔄 Version History

### v2.0 (Current - app.py)
- Complete refactoring
- Modular architecture
- Performance optimizations
- Enhanced features
- Full test coverage
- Comprehensive documentation

### v1.0 (Preserved - appv1.py)
- Original hackathon MVP
- Single-file application
- Core functionality
- Basic features

## 📚 Related Documentation

- **Quick Start**: [QUICK_START.md](QUICK_START.md)
- **Migration**: [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)
- **Architecture**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **Full Index**: [INDEX.md](INDEX.md)

## ✅ Checklist for New Users

- [ ] Clone repository
- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Run main app: `streamlit run app.py`
- [ ] Explore features
- [ ] (Optional) Compare with v1.0: `streamlit run appv1.py`
- [ ] Read documentation starting with [QUICK_START.md](QUICK_START.md)

## 🎉 Summary

**Main Application**: `app.py` (Enhanced v2.0)  
**Original Version**: `appv1.py` (Preserved v1.0)  
**Deployment**: Use `app.py` (automatically detected by Streamlit Cloud)  
**Development**: Both versions available for testing and comparison

---

**Last Updated**: 2025-10-07  
**Current Version**: 2.0.0  
**Status**: ✅ Production Ready
