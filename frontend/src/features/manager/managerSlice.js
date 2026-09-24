import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import api from '../../services/api';

export const fetchManagerDashboard = createAsyncThunk(
  'manager/fetchDashboard',
  async (date, { rejectWithValue }) => {
    try {
      const params = date ? { date } : {};
      const response = await api.get('/manager-dashboard/', { params });
      return response.data;
    } catch (err) {
      return rejectWithValue(err.response?.data || err.message);
    }
  }
);

const managerSlice = createSlice({
  name: 'manager',
  initialState: {
    dashboard: null,
    loading: false,
    error: null,
  },
  reducers: {
    clearDashboard: (state) => {
      state.dashboard = null;
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchManagerDashboard.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchManagerDashboard.fulfilled, (state, action) => {
        state.loading = false;
        state.dashboard = action.payload;
      })
      .addCase(fetchManagerDashboard.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || action.error.message;
      });
  },
});

export const { clearDashboard } = managerSlice.actions;
export default managerSlice.reducer;
