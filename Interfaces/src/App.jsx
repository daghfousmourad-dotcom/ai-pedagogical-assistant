import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import LoginProf from './pages/LoginProf';
import ProfDashboard from './pages/ProfDashboard';
import LoginAdmin from './pages/LoginAdmin';
import AdminDashboard from './pages/AdminDashboard';
import CourseSession from './pages/CourseSession';
import Starter from './pages/Starter';
import SuperSession from './pages/SuperSession';
import MLOpsDashboard from './pages/MLOpsDashboard';
import MLOpsMonitoring from './pages/MLOpsMonitoring';
import PDFProjectorView from './pages/PDFProjectorView';

function App() {
    return (
        <Router>
            <Routes>
                <Route path="/login" element={<LoginProf />} />
                <Route path="/dashboard" element={<ProfDashboard />} />
                <Route path="/admin-login" element={<LoginAdmin />} />
                <Route path="/admin-dashboard" element={<AdminDashboard />} />
                <Route path="/mlops-admin" element={<MLOpsDashboard />} />
                <Route path="/mlops-monitoring" element={<MLOpsMonitoring />} />
                <Route path="/starter.html" element={<Starter />} />
                <Route path="/session/:courseId/:docId" element={<CourseSession />} />
                <Route path="/super-session/:courseId/:docId" element={<SuperSession />} />
                <Route path="/pdf-projector/:docId" element={<PDFProjectorView />} />
                <Route path="/" element={<Navigate to="/login" />} />
            </Routes>
        </Router>
    );
}

export default App;